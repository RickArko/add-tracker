"""Turns raw entries into trend numbers. Pure functions, no database access.

Calendar days are always the user's local days. Days before tracking began are excluded rather
than counted as zero, because a false run of zeros would flatter every early average.
"""

from collections import Counter, defaultdict
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
) -> dict[str, Any]:
    today = now.astimezone(tz).date()
    local_days = [e.occurred_at.astimezone(tz).date() for e in entries]
    first_day = min([created_at.astimezone(tz).date(), *local_days])
    window_start = max(today - timedelta(days=days - 1), first_day)

    amount_by_day: dict[date, float] = defaultdict(float)
    uses_by_day: Counter[date] = Counter()
    urges_by_day: Counter[date] = Counter()
    for entry, day in zip(entries, local_days, strict=True):
        if entry.kind == "use":
            amount_by_day[day] += entry.amount or 0
            uses_by_day[day] += 1
        else:
            urges_by_day[day] += 1

    def average_ending(day: date) -> float:
        start = max(day - timedelta(days=6), first_day)
        span = (day - start).days + 1
        return sum(amount_by_day.get(start + timedelta(days=i), 0) for i in range(span)) / span

    daily = []
    for offset in range((today - window_start).days + 1):
        day = window_start + timedelta(days=offset)
        daily.append(
            {
                "date": day.isoformat(),
                "amount": round(amount_by_day.get(day, 0), 3),
                "uses": uses_by_day.get(day, 0),
                "urges": urges_by_day.get(day, 0),
                "average_7d": round(average_ending(day), 3),
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
    if recent_7 is not None and previous_7:
        change_pct = round((recent_7 - previous_7) / previous_7 * 100)

    limit = 0.0 if goal == "quit" else daily_limit
    finished = [d for d in daily if d["date"] < today.isoformat()]
    within_goal = None
    if limit is not None:
        within_goal = {
            "days": sum(d["amount"] <= limit for d in finished),
            "of": len(finished),
            "limit": limit,
        }

    use_times = sorted(e.occurred_at for e in entries if e.kind == "use")
    gaps = [b - a for a, b in zip(use_times, use_times[1:], strict=False)]
    if use_times:
        gaps.append(now - use_times[-1])
    longest_gap_hours = round(max(gaps).total_seconds() / 3600, 1) if gaps else None

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
        },
    }
