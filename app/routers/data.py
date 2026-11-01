import csv
import io
import json
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import now_utc
from app.models import Entry, Tracker, User
from app.schemas import (
    EntryCreate,
    EntryOut,
    EntryUpdate,
    TodayTracker,
    TrackerCreate,
    TrackerOut,
    TrackerUpdate,
)
from app.security import current_user, get_db
from app.stats import EntryRow, compute_stats, day_bounds

router = APIRouter(prefix="/api", tags=["data"])

# Tolerates clock skew between device and server, while still catching mistaken future dates.
FUTURE_TOLERANCE = timedelta(minutes=5)


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


def _check_not_future(when: datetime) -> None:
    if when > now_utc() + FUTURE_TOLERANCE:
        raise HTTPException(status_code=422, detail="Time can't be in the future.")


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
    body: TrackerCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> TrackerOut:
    values = body.model_dump()
    if values["goal"] == "quit":
        values["daily_limit"] = None
    tracker = Tracker(user_id=user.id, created_at=now_utc(), **values)
    db.add(tracker)
    db.commit()
    return tracker


@router.patch("/trackers/{tracker_id}")
def update_tracker(
    tracker_id: int,
    body: TrackerUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> TrackerOut:
    tracker = _owned_tracker(db, user, tracker_id)
    changes = body.model_dump(exclude_unset=True)
    if "archived" in changes:
        archived = changes.pop("archived")
        tracker.archived_at = now_utc() if archived else None
    for field, value in changes.items():
        if value is None and field != "daily_limit":
            raise HTTPException(status_code=422, detail=f"{field} can't be empty.")
        setattr(tracker, field, value)
    if tracker.goal == "quit":
        tracker.daily_limit = None
    db.commit()
    return tracker


@router.delete("/trackers/{tracker_id}", status_code=204)
def delete_tracker(
    tracker_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(_owned_tracker(db, user, tracker_id))
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
        )
        for t in trackers
    ]


# --- Entries ---


@router.get("/entries")
def list_entries(
    tracker_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
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
    occurred_at = body.occurred_at or now_utc()
    _check_not_future(occurred_at)
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
    )
    db.add(entry)
    db.commit()
    return entry


@router.patch("/entries/{entry_id}")
def update_entry(
    entry_id: int,
    body: EntryUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> EntryOut:
    entry = _owned_entry(db, user, entry_id)
    changes = body.model_dump(exclude_unset=True)
    if "occurred_at" in changes:
        _check_not_future(changes["occurred_at"])
    if "amount" in changes:
        if entry.kind == "urge" and changes["amount"] is not None:
            raise HTTPException(status_code=422, detail="Urges don't have an amount.")
        if entry.kind == "use" and changes["amount"] is None:
            raise HTTPException(status_code=422, detail="Enter an amount.")
    for field, value in changes.items():
        setattr(entry, field, value or None if field in ("trigger", "note") else value)
    db.commit()
    return entry


@router.delete("/entries/{entry_id}", status_code=204)
def delete_entry(
    entry_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> None:
    db.delete(_owned_entry(db, user, entry_id))
    db.commit()


# --- Trends ---


@router.get("/trackers/{tracker_id}/stats")
def tracker_stats(
    tracker_id: int,
    days: Annotated[int, Query(ge=7, le=365)] = 30,
    tz: ZoneInfo = Depends(parse_tz),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    tracker = _owned_tracker(db, user, tracker_id)
    rows = db.execute(
        select(Entry.kind, Entry.occurred_at, Entry.amount, Entry.craving, Entry.trigger).where(
            Entry.tracker_id == tracker.id
        )
    ).all()
    return compute_stats(
        goal=tracker.goal,
        daily_limit=tracker.daily_limit,
        created_at=tracker.created_at,
        entries=[EntryRow(*row) for row in rows],
        days=days,
        tz=tz,
        now=now_utc(),
    )


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
        "entries": [
            EntryOut.model_validate(e).model_dump(mode="json") for e, _t in _export_rows(db, user)
        ],
    }
    return Response(
        json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="tally-export.json"'},
    )
