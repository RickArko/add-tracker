"""Turns raw entries into trend numbers. Pure functions, no database access.

A finished day counts only once it's accounted for: it has a log, or was confirmed as having no
use. A blank day earns nothing, so not logging can never beat logging, and adding a forgotten log
to a blank day can't lower level progress.

Calendar days are always the user's local days. Goal figures, comparisons and gaps start when the
tracker was created. An unlogged day before then isn't a day without use, it just wasn't recorded,
so one backdated entry (or a mistyped year) can't invent months of flattering zeros. Backdated
entries still appear on the chart.
"""

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class EntryRow:
    kind: str
    occurred_at: datetime
    amount: float | None = None
    craving: int | None = None
    trigger: str | None = None


@dataclass(frozen=True)
class PeriodRow:
    starts_on: date
    goal: str
    daily_limit: float | None

    @property
    def limit(self) -> float | None:
        return 0.0 if self.goal == "quit" else self.daily_limit


@dataclass(frozen=True)
class PlanRow:
    baseline: float
    step: float
    clear_days: int
    started_on: date


# Thresholds for milestones. They're derived from the log and only ever go up, except when
# entries are deleted, because a hard day must never cost someone what they've already done.
MILESTONES = {
    "gap": [6, 12, 24, 48, 72, 168, 336, 720, 2160],
    "urges": [1, 10, 25, 50, 100, 250],
    "within": [1, 7, 14, 30, 60, 100, 200],
    "logged": [3, 7, 14, 30, 60, 100, 200],
}


def milestone(key: str, value: float) -> dict[str, Any]:
    targets = MILESTONES[key]
    return {
        "key": key,
        "value": round(value, 1),
        "earned": sum(value >= t for t in targets),
        "total": len(targets),
        "next": next((t for t in targets if value < t), None),
    }


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """The instants a local calendar day starts and ends, which handles 23- and 25-hour days."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)
    return start, end


def compute_stats(
    *,
    goal: str,
    daily_limit: float | None,
    created_at: datetime,
    entries: list[EntryRow],
    days: int,
    tz: ZoneInfo,
    now: datetime,
    periods: Sequence[PeriodRow] = (),
    plan: PlanRow | None = None,
    confirmed_days: Iterable[date] = (),
) -> dict[str, Any]:
    today = now.astimezone(tz).date()
    local_days = [e.occurred_at.astimezone(tz).date() for e in entries]
    first_day = created_at.astimezone(tz).date()
    earliest_day = min([first_day, *local_days])
    window_start = max(today - timedelta(days=days - 1), earliest_day)

    amount_by_day: dict[date, float] = defaultdict(float)
    uses_by_day: Counter[date] = Counter()
    urges_by_day: Counter[date] = Counter()
    for entry, day in zip(entries, local_days, strict=True):
        if entry.kind == "use":
            amount_by_day[day] += entry.amount or 0
            uses_by_day[day] += 1
        else:
            urges_by_day[day] += 1

    ordered_periods = sorted(periods, key=lambda p: p.starts_on)
    current_limit = 0.0 if goal == "quit" else daily_limit

    accounted = set(local_days) | set(confirmed_days)

    def counts(day: date) -> bool:
        return day in accounted or day >= today

    def limit_on(day: date) -> float | None:
        """The limit in force that day. Days before any period use the earliest one."""
        if not ordered_periods:
            return current_limit
        chosen = ordered_periods[0]
        for period in ordered_periods:
            if period.starts_on <= day:
                chosen = period
        return chosen.limit

    def average_ending(day: date) -> float | None:
        # Backdated days average among themselves; they don't dilute the tracked period.
        start = max(day - timedelta(days=6), first_day if day >= first_day else earliest_day)
        span = [start + timedelta(days=i) for i in range((day - start).days + 1)]
        known = [d for d in span if counts(d)]
        if not known:
            return None
        return sum(amount_by_day.get(d, 0) for d in known) / len(known)

    daily = []
    for offset in range((today - window_start).days + 1):
        day = window_start + timedelta(days=offset)
        daily.append(
            {
                "date": day.isoformat(),
                "amount": round(amount_by_day.get(day, 0), 3),
                "uses": uses_by_day.get(day, 0),
                "urges": urges_by_day.get(day, 0),
                "average_7d": None if (avg := average_ending(day)) is None else round(avg, 3),
                "limit": limit_on(day),
            }
        )

    in_window = [
        (entry, day)
        for entry, day in zip(entries, local_days, strict=True)
        if window_start <= day <= today
    ]

    # weekday (Monday = 0) by hour of use count
    heatmap = [[0] * 24 for _ in range(7)]
    triggers: dict[str, dict[str, int]] = defaultdict(lambda: {"uses": 0, "urges": 0})
    cravings = []
    for entry, _day in in_window:
        if entry.kind == "use":
            local = entry.occurred_at.astimezone(tz)
            heatmap[local.weekday()][local.hour] += 1
        if entry.trigger:
            triggers[entry.trigger]["uses" if entry.kind == "use" else "urges"] += 1
        if entry.craving is not None:
            cravings.append(entry.craving)

    def total(first: date, last: date) -> float | None:
        """Sum across a whole-day range, or None if tracking hadn't begun by its first day."""
        if first < first_day:
            return None
        span = (last - first).days + 1
        return sum(amount_by_day.get(first + timedelta(days=i), 0) for i in range(span))

    # Compare finished days only, so a part-finished today can't look like an improvement.
    yesterday = today - timedelta(days=1)
    recent_7 = total(today - timedelta(days=7), yesterday)
    previous_7 = total(today - timedelta(days=14), today - timedelta(days=8))
    change_pct = None
    weeks_complete = all(counts(today - timedelta(days=i)) for i in range(1, 15))
    if recent_7 is not None and previous_7 and weeks_complete:
        change_pct = round((recent_7 - previous_7) / previous_7 * 100)

    finished = [
        d
        for d in daily
        if first_day.isoformat() <= d["date"] < today.isoformat()
        and d["limit"] is not None
        and counts(date.fromisoformat(d["date"]))
    ]
    within_goal = None
    if finished or current_limit is not None:
        within_goal = {
            "days": sum(d["amount"] <= d["limit"] for d in finished),
            "of": len(finished),
            "limit": current_limit,
        }

    use_times = sorted(e.occurred_at for e in entries if e.kind == "use")
    marks = [created_at, *(t for t in use_times if t >= created_at), now]

    def verified(a: datetime, b: datetime) -> bool:
        """A stretch counts only if every whole day inside it is accounted for."""
        first, last = a.astimezone(tz).date(), b.astimezone(tz).date()
        inside = (first + timedelta(days=i) for i in range(1, (last - first).days))
        return all(counts(day) for day in inside)

    longest_gap_hours = round(
        max(
            (
                (b - a).total_seconds() / 3600
                for a, b in zip(marks, marks[1:], strict=False)
                if verified(a, b)
            ),
            default=0.0,
        ),
        1,
    )
    unlogged = [
        day
        for day in (today - timedelta(days=i) for i in range(1, 8))
        if day >= first_day and day not in accounted
    ]

    tracked_days = [first_day + timedelta(days=i) for i in range(max(0, (today - first_day).days))]
    game = _game(
        tracked_days=[day for day in tracked_days if counts(day)],
        all_days=tracked_days,
        unlogged=unlogged,
        amount_by_day=amount_by_day,
        limit_on=limit_on,
        current_limit=current_limit,
        plan=plan,
        period_start=ordered_periods[-1].starts_on if ordered_periods else None,
        use_times=use_times,
        longest_gap_hours=longest_gap_hours,
        total_urges=sum(urges_by_day.values()),
        days_logged=len({d for e, d in zip(entries, local_days, strict=True)}),
        today=today,
        now=now,
    )

    return {
        "window_start": window_start.isoformat(),
        "daily": daily,
        "heatmap": heatmap,
        "triggers": sorted(
            ({"trigger": name, **counts} for name, counts in triggers.items()),
            key=lambda row: (-(row["uses"] + row["urges"]), row["trigger"]),
        )[:8],
        "summary": {
            "amount_in_window": round(sum(d["amount"] for d in daily), 3),
            "uses_in_window": sum(d["uses"] for d in daily),
            "urges_in_window": sum(d["urges"] for d in daily),
            "average_craving": round(sum(cravings) / len(cravings), 1) if cravings else None,
            "recent_7": None if recent_7 is None else round(recent_7, 3),
            "previous_7": None if previous_7 is None else round(previous_7, 3),
            "change_pct": change_pct,
            "within_goal": within_goal,
            "last_use_at": use_times[-1].isoformat() if use_times else None,
            "longest_gap_hours": longest_gap_hours,
            "unlogged_days": sum(1 for d in daily if not counts(date.fromisoformat(d["date"]))),
        },
        "game": game,
    }


def next_level_limit(current_limit: float, plan: PlanRow) -> float:
    return round(max(0.0, min(current_limit - plan.step, plan.baseline)), 3)


def _plan_progress(
    *,
    tracked_days: list[date],
    amount_by_day: dict[date, float],
    current_limit: float,
    plan: PlanRow,
    period_start: date | None,
    today: date,
) -> dict[str, Any]:
    # Days within the limit add up rather than needing to be in a row, so a hard day delays a
    # level without undoing it.
    start = max(period_start or plan.started_on, plan.started_on)
    cleared = sum(
        amount_by_day.get(day, 0) <= current_limit for day in tracked_days if day >= start
    )
    banked = sum(
        max(0.0, plan.baseline - amount_by_day.get(day, 0))
        for day in tracked_days
        if day >= plan.started_on
    )
    steps_left = math.ceil(round(current_limit / plan.step, 6))
    days_left = max(0, plan.clear_days - cleared)
    at_zero = current_limit <= 0
    return {
        "level": max(1, math.ceil(round((plan.baseline - current_limit) / plan.step, 6)) + 1),
        "total_levels": math.ceil(round(plan.baseline / plan.step, 6)) + 1,
        "limit": current_limit,
        "next_limit": None if at_zero else next_level_limit(current_limit, plan),
        "days_cleared": cleared,
        "clear_days": plan.clear_days,
        "ready": not at_zero and cleared >= plan.clear_days,
        "at_zero": at_zero,
        "banked": round(banked, 3),
        "baseline": plan.baseline,
        "zero_by": None
        if at_zero
        else (today + timedelta(days=days_left + (steps_left - 1) * plan.clear_days)).isoformat(),
    }


def _trend(
    tracked_days: list[date], amount_by_day: dict[date, float], today: date
) -> dict[str, Any] | None:
    """A least-squares line through the last 28 finished days. Needs 14 to say anything."""
    days = [day for day in tracked_days if (today - day).days <= 28]
    if len(days) < 14:
        return None
    ys = [amount_by_day.get(day, 0) for day in days]
    xs = [(day - today).days for day in days]
    slope, fitted_today = statistics.linear_regression(xs, ys)
    zero_by = None
    if slope < 0 and fitted_today > 0:
        days_to_zero = fitted_today / -slope
        if days_to_zero < 1825:
            zero_by = (today + timedelta(days=math.ceil(days_to_zero))).isoformat()
    return {"per_week": round(slope * 7, 2), "days_used": len(days), "zero_by": zero_by}


def _game(
    *,
    tracked_days: list[date],
    all_days: list[date],
    unlogged: list[date],
    amount_by_day: dict[date, float],
    limit_on,
    current_limit: float | None,
    plan: PlanRow | None,
    period_start: date | None,
    use_times: list[datetime],
    longest_gap_hours: float,
    total_urges: int,
    days_logged: int,
    today: date,
    now: datetime,
) -> dict[str, Any]:
    amounts = [amount_by_day.get(day, 0) for day in tracked_days]

    # The first day is left out: it's usually partial, so its low count would be unbeatable.
    complete = all_days[1:]
    known = set(tracked_days)
    lowest_day = None
    candidates = [day for day in complete if day in known]
    if candidates:
        low = min(amount_by_day.get(day, 0) for day in candidates)
        # The latest day wins a tie, so matching a record shows as recent.
        when = max(day for day in candidates if amount_by_day.get(day, 0) == low)
        lowest_day = {"amount": round(low, 3), "date": when.isoformat()}

    lowest_week = None
    weeks = [
        complete[i : i + 7]
        for i in range(len(complete) - 6)
        if all(day in known for day in complete[i : i + 7])
    ]
    if weeks:
        totals = [sum(amount_by_day.get(day, 0) for day in week) for week in weeks]
        low = min(totals)
        last = max(i for i, total in enumerate(totals) if total == low)
        lowest_week = {"amount": round(low, 3), "ending": weeks[last][-1].isoformat()}

    recent = [t for t in use_times if t >= now - timedelta(days=7)]
    gaps = [(b - a).total_seconds() / 3600 for a, b in zip(recent, recent[1:], strict=False)]
    typical_gap_hours = round(statistics.median(gaps), 2) if len(gaps) >= 3 else None

    within = 0
    for day, amount in zip(tracked_days, amounts, strict=True):
        limit = limit_on(day)
        if limit is not None and amount <= limit:
            within += 1

    level = None
    if plan is not None and current_limit is not None:
        level = _plan_progress(
            tracked_days=tracked_days,
            amount_by_day=amount_by_day,
            current_limit=current_limit,
            plan=plan,
            period_start=period_start,
            today=today,
        )

    return {
        "level": level,
        "trend": _trend(tracked_days, amount_by_day, today),
        "records": {
            "lowest_day": lowest_day,
            "lowest_week": lowest_week,
            "longest_gap_hours": longest_gap_hours,
        },
        "typical_gap_hours": typical_gap_hours,
        "unlogged_recent": [day.isoformat() for day in unlogged],
        "milestones": [
            milestone("gap", longest_gap_hours),
            milestone("urges", total_urges),
            milestone("within", within),
            milestone("logged", days_logged),
        ],
    }
