import csv
import io
import json
from datetime import UTC, date, datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import now_utc
from app.models import Entry, LimitPeriod, NoUseDay, Tracker, User
from app.schemas import (
    EntryCreate,
    EntryOut,
    EntryUpdate,
    NoUseBody,
    PlanBody,
    TodayTracker,
    TrackerCreate,
    TrackerOut,
    TrackerUpdate,
)
from app.security import current_user, get_db
from app.stats import (
    EntryRow,
    PeriodRow,
    PlanRow,
    compute_stats,
    day_bounds,
    next_level_limit,
)

router = APIRouter(prefix="/api", tags=["data"])

# Tapering these can be dangerous, so the app never sets a pace for them.
CLINICIAN_ONLY_TAPER = {"alcohol", "benzodiazepine", "opioid"}

# Tolerates clock skew between device and server, while still catching mistaken future dates.
FUTURE_TOLERANCE = timedelta(minutes=5)
EARLIEST_ENTRY = datetime(2000, 1, 1, tzinfo=UTC)
DbId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def parse_tz(tz: str = Query("UTC", max_length=64)) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail="Unknown time zone.") from exc


def _owned_tracker(db: Session, user: User, tracker_id: int) -> Tracker:
    tracker = db.get(Tracker, tracker_id)
    if tracker is None or tracker.user_id != user.id:
        raise HTTPException(status_code=404, detail="Tracker not found.")
    return tracker


def _owned_entry(db: Session, user: User, entry_id: int) -> Entry:
    entry = db.get(Entry, entry_id)
    if entry is None or entry.tracker.user_id != user.id:
        raise HTTPException(status_code=404, detail="Entry not found.")
    return entry


def _check_entry_time(when: datetime) -> None:
    if when < EARLIEST_ENTRY:
        raise HTTPException(status_code=422, detail="Check the year: that date is too far back.")
    if when > now_utc() + FUTURE_TOLERANCE:
        raise HTTPException(status_code=422, detail="Time can't be in the future.")


def _local_today(tz: ZoneInfo) -> str:
    return now_utc().astimezone(tz).date().isoformat()


def _record_period(db: Session, tracker: Tracker, tz: ZoneInfo) -> bool:
    """Notes a new limit from today on. Returns whether the limit in force changed.

    Goal changes that leave the limit alone are stored on the latest period, so they don't
    restart progress on a level.
    """
    db.flush()
    effective = 0.0 if tracker.goal == "quit" else tracker.daily_limit
    recent = db.scalars(
        select(LimitPeriod)
        .where(LimitPeriod.tracker_id == tracker.id)
        .order_by(LimitPeriod.starts_on.desc())
        .limit(2)
    ).all()
    latest = recent[0] if recent else None
    today = _local_today(tz)
    if latest is not None:
        previous = 0.0 if latest.goal == "quit" else latest.daily_limit
        if previous == effective:
            latest.goal = tracker.goal
            return False
        if latest.starts_on >= today:
            # Going back to the earlier limit the same day undoes a mistake, so progress at
            # that limit carries on as though the change never happened.
            if len(recent) == 2:
                before = recent[1]
                if (0.0 if before.goal == "quit" else before.daily_limit) == effective:
                    before.goal = tracker.goal
                    db.delete(latest)
                    return True
            latest.goal, latest.daily_limit = tracker.goal, tracker.daily_limit
            return True
    db.add(
        LimitPeriod(
            tracker_id=tracker.id,
            starts_on=today,
            goal=tracker.goal,
            daily_limit=tracker.daily_limit,
        )
    )
    return True


def _stats_for(db: Session, tracker: Tracker, days: int, tz: ZoneInfo) -> dict:
    rows = db.execute(
        select(Entry.kind, Entry.occurred_at, Entry.amount, Entry.craving, Entry.trigger).where(
            Entry.tracker_id == tracker.id
        )
    ).all()
    periods = db.scalars(select(LimitPeriod).where(LimitPeriod.tracker_id == tracker.id)).all()
    confirmed = db.scalars(select(NoUseDay.day).where(NoUseDay.tracker_id == tracker.id)).all()
    plan = _plan_row(tracker)
    return compute_stats(
        goal=tracker.goal,
        daily_limit=tracker.daily_limit,
        created_at=tracker.created_at,
        entries=[EntryRow(*row) for row in rows],
        days=days,
        tz=tz,
        now=now_utc(),
        periods=[
            PeriodRow(date.fromisoformat(p.starts_on), p.goal, p.daily_limit) for p in periods
        ],
        plan=plan,
        confirmed_days=[date.fromisoformat(day) for day in confirmed],
    )


def _plan_row(tracker: Tracker) -> PlanRow | None:
    plan = None
    if tracker.step_amount and tracker.baseline_amount and tracker.plan_started_on:
        plan = PlanRow(
            baseline=tracker.baseline_amount,
            step=tracker.step_amount,
            clear_days=tracker.clear_days or 7,
            started_on=date.fromisoformat(tracker.plan_started_on),
        )
    return plan


# --- Trackers ---


@router.get("/trackers")
def list_trackers(
    include_archived: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TrackerOut]:
    query = select(Tracker).where(Tracker.user_id == user.id).order_by(Tracker.id)
    if not include_archived:
        query = query.where(Tracker.archived_at.is_(None))
    return list(db.scalars(query))


@router.post("/trackers", status_code=201)
def create_tracker(
    body: TrackerCreate,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TrackerOut:
    values = body.model_dump()
    if values["goal"] == "quit":
        values["daily_limit"] = None
    tracker = Tracker(user_id=user.id, created_at=now_utc(), **values)
    db.add(tracker)
    _record_period(db, tracker, tz)
    db.commit()
    return tracker


@router.patch("/trackers/{tracker_id}")
def update_tracker(
    tracker_id: DbId,
    body: TrackerUpdate,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TrackerOut:
    tracker = _owned_tracker(db, user, tracker_id)
    changes = body.model_dump(exclude_unset=True)
    if "archived" in changes:
        archived = changes.pop("archived")
        if archived is not None:
            tracker.archived_at = now_utc() if archived else None
    for field, value in changes.items():
        if value is None and field != "daily_limit":
            raise HTTPException(status_code=422, detail=f"{field} can't be empty.")
        setattr(tracker, field, value)
    if tracker.goal == "quit":
        tracker.daily_limit = None
    if tracker.step_amount and tracker.category in CLINICIAN_ONLY_TAPER:
        _clear_plan(tracker)
    _record_period(db, tracker, tz)
    db.commit()
    return tracker


def _clear_plan(tracker: Tracker) -> None:
    tracker.baseline_amount = tracker.step_amount = tracker.clear_days = None
    tracker.plan_started_on = None


@router.put("/trackers/{tracker_id}/plan")
def set_plan(
    tracker_id: DbId,
    body: PlanBody,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TrackerOut:
    tracker = _owned_tracker(db, user, tracker_id)
    if tracker.category in CLINICIAN_ONLY_TAPER:
        raise HTTPException(
            status_code=422,
            detail="Levels aren't available for this, because tapering it needs a clinician.",
        )
    if body.step_amount > body.baseline_amount:
        raise HTTPException(status_code=422, detail="Each step must be smaller than your start.")
    tracker.baseline_amount = body.baseline_amount
    tracker.step_amount = body.step_amount
    tracker.clear_days = body.clear_days
    # Changing a plan keeps its start, so tuning the pace doesn't wipe what's banked.
    tracker.plan_started_on = tracker.plan_started_on or _local_today(tz)
    if tracker.daily_limit is None or tracker.daily_limit > body.baseline_amount:
        tracker.daily_limit = body.baseline_amount
    if tracker.goal == "quit":
        tracker.daily_limit = body.baseline_amount
    tracker.goal = "reduce"
    _record_period(db, tracker, tz)
    db.commit()
    return tracker


@router.delete("/trackers/{tracker_id}/plan")
def remove_plan(
    tracker_id: DbId, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TrackerOut:
    tracker = _owned_tracker(db, user, tracker_id)
    _clear_plan(tracker)
    db.commit()
    return tracker


@router.post("/trackers/{tracker_id}/step-down")
def step_down(
    tracker_id: DbId,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TrackerOut:
    tracker = _owned_tracker(db, user, tracker_id)
    plan = _plan_row(tracker)
    if plan is None or not tracker.daily_limit:
        raise HTTPException(status_code=422, detail="There's no lower level to move to.")
    # Also stops a double tap from dropping two levels. A limit can still be lowered in Settings.
    if not _stats_for(db, tracker, 7, tz)["game"]["level"]["ready"]:
        raise HTTPException(status_code=422, detail="This level isn't cleared yet.")
    next_limit = next_level_limit(tracker.daily_limit, plan)
    if next_limit == 0:
        tracker.goal, tracker.daily_limit = "quit", None
    else:
        tracker.goal, tracker.daily_limit = "reduce", next_limit
    _record_period(db, tracker, tz)
    db.commit()
    return tracker


@router.delete("/trackers/{tracker_id}", status_code=204)
def delete_tracker(
    tracker_id: DbId, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(_owned_tracker(db, user, tracker_id))
    db.commit()


@router.post("/trackers/{tracker_id}/no-use-days", status_code=204)
def confirm_no_use(
    tracker_id: DbId,
    body: NoUseBody,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    tracker = _owned_tracker(db, user, tracker_id)
    day = body.day.isoformat()
    if day >= _local_today(tz):
        raise HTTPException(status_code=422, detail="Only a finished day can be confirmed.")
    start, end = day_bounds(body.day, tz)
    used = db.scalar(
        select(func.count())
        .select_from(Entry)
        .where(
            Entry.tracker_id == tracker.id,
            Entry.kind == "use",
            Entry.occurred_at >= start,
            Entry.occurred_at < end,
        )
    )
    if used:
        raise HTTPException(status_code=422, detail="That day already has a logged use.")
    db.merge(NoUseDay(tracker_id=tracker.id, day=day))
    db.commit()


# --- Today ---


@router.get("/today")
def today(
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[TodayTracker]:
    start, end = day_bounds(now_utc().astimezone(tz).date(), tz)
    trackers = db.scalars(
        select(Tracker)
        .where(Tracker.user_id == user.id, Tracker.archived_at.is_(None))
        .order_by(Tracker.id)
    ).all()
    ids = [t.id for t in trackers]

    totals = db.execute(
        select(Entry.tracker_id, Entry.kind, func.count(), func.coalesce(func.sum(Entry.amount), 0))
        .where(Entry.tracker_id.in_(ids), Entry.occurred_at >= start, Entry.occurred_at < end)
        .group_by(Entry.tracker_id, Entry.kind)
    ).all()
    last_uses = dict(
        db.execute(
            select(Entry.tracker_id, func.max(Entry.occurred_at))
            .where(Entry.tracker_id.in_(ids), Entry.kind == "use")
            .group_by(Entry.tracker_id)
        ).all()
    )
    by_key = {(tracker_id, kind): (n, amt) for tracker_id, kind, n, amt in totals}
    return [
        TodayTracker(
            **TrackerOut.model_validate(t).model_dump(),
            uses_today=by_key.get((t.id, "use"), (0, 0))[0],
            amount_today=round(by_key.get((t.id, "use"), (0, 0))[1], 3),
            urges_today=by_key.get((t.id, "urge"), (0, 0))[0],
            last_use_at=last_uses.get(t.id),
            game=_stats_for(db, t, 7, tz)["game"],
        )
        for t in trackers
    ]


# --- Entries ---


@router.get("/entries")
def list_entries(
    tracker_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=2**62)] = 0,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> list[EntryOut]:
    query = (
        select(Entry)
        .join(Tracker)
        .where(Tracker.user_id == user.id)
        .order_by(Entry.occurred_at.desc(), Entry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    if tracker_id is not None:
        query = query.where(Entry.tracker_id == tracker_id)
    return list(db.scalars(query))


@router.post("/entries", status_code=201)
def create_entry(
    body: EntryCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> EntryOut:
    tracker = _owned_tracker(db, user, body.tracker_id)
    if body.client_id:
        existing = _by_client_id(db, tracker.id, body.client_id)
        if existing is not None:
            return existing
    occurred_at = body.occurred_at or now_utc()
    _check_entry_time(occurred_at)
    amount = None
    if body.kind == "use":
        # Copied onto the entry, so editing the tracker's default later can't rewrite history.
        amount = body.amount if body.amount is not None else tracker.default_amount
    entry = Entry(
        tracker_id=tracker.id,
        kind=body.kind,
        occurred_at=occurred_at,
        amount=amount,
        craving=body.craving,
        trigger=body.trigger or None,
        note=body.note or None,
        client_id=body.client_id,
    )
    db.add(entry)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _by_client_id(db, tracker.id, body.client_id)
    return entry


def _by_client_id(db: Session, tracker_id: int, client_id: str | None) -> Entry | None:
    return db.scalar(
        select(Entry).where(Entry.tracker_id == tracker_id, Entry.client_id == client_id)
    )


@router.patch("/entries/{entry_id}")
def update_entry(
    entry_id: DbId,
    body: EntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EntryOut:
    entry = _owned_entry(db, user, entry_id)
    changes = body.model_dump(exclude_unset=True)
    if "occurred_at" in changes:
        _check_entry_time(changes["occurred_at"])
    if "amount" in changes:
        if entry.kind == "urge" and changes["amount"] is not None:
            raise HTTPException(status_code=422, detail="Urges don't have an amount.")
        if entry.kind == "use" and changes["amount"] is None:
            raise HTTPException(status_code=422, detail="Enter an amount.")
    for field, value in changes.items():
        setattr(entry, field, value or None if field in ("trigger", "note") else value)
    db.commit()
    return entry


@router.delete("/entries/by-client/{client_id}", status_code=204)
def delete_entry_by_client(
    client_id: Annotated[str, Path(min_length=8, max_length=64)],
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> None:
    """Undo for a log whose reply was lost. Succeeds whether or not the log ever arrived."""
    entry = db.scalar(
        select(Entry).join(Tracker).where(Entry.client_id == client_id, Tracker.user_id == user.id)
    )
    if entry is not None:
        db.delete(entry)
        db.commit()


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(
    entry_id: DbId, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(_owned_entry(db, user, entry_id))
    db.commit()


# --- Trends ---


@router.get("/trackers/{tracker_id}/stats")
def tracker_stats(
    tracker_id: DbId,
    days: Annotated[int, Query(ge=7, le=365)] = 30,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    tracker = _owned_tracker(db, user, tracker_id)
    return _stats_for(db, tracker, days, tz)


# --- Export ---


def _export_rows(db: Session, user: User):
    return db.execute(
        select(Entry, Tracker)
        .join(Tracker)
        .where(Tracker.user_id == user.id)
        .order_by(Entry.occurred_at)
    ).all()


def _csv_safe(value: str | None) -> str:
    """Stops a note beginning with =, + and so on running as a formula in a spreadsheet."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value or ""


@router.get("/export.csv")
def export_csv(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        ["occurred_at_utc", "tracker", "kind", "amount", "unit", "craving", "trigger", "note"]
    )
    for entry, tracker in _export_rows(db, user):
        writer.writerow(
            [
                entry.occurred_at.isoformat(),
                _csv_safe(tracker.name),
                entry.kind,
                "" if entry.amount is None else entry.amount,
                _csv_safe(tracker.unit),
                "" if entry.craving is None else entry.craving,
                _csv_safe(entry.trigger),
                _csv_safe(entry.note),
            ]
        )
    return Response(
        out.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="tally-export.csv"'},
    )


@router.get("/export.json")
def export_json(user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    trackers = db.scalars(select(Tracker).where(Tracker.user_id == user.id)).all()
    payload = {
        "exported_at": now_utc().isoformat(),
        "username": user.username,
        "trackers": [TrackerOut.model_validate(t).model_dump(mode="json") for t in trackers],
        "limit_history": [
            {
                "tracker_id": p.tracker_id,
                "starts_on": p.starts_on,
                "goal": p.goal,
                "daily_limit": p.daily_limit,
            }
            for p in db.scalars(
                select(LimitPeriod)
                .where(LimitPeriod.tracker_id.in_([t.id for t in trackers]))
                .order_by(LimitPeriod.tracker_id, LimitPeriod.starts_on)
            )
        ],
        "entries": [
            EntryOut.model_validate(e).model_dump(mode="json") for e, _t in _export_rows(db, user)
        ],
    }
    return Response(
        json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="tally-export.json"'},
    )
