from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.stats import EntryRow, compute_stats, day_bounds

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 6, 15, 16, 0, tzinfo=UTC)  # noon in New York, a Monday


def use(when, amount=1.0, **kw):
    return EntryRow("use", when, amount, **kw)


def run(entries=(), *, goal="reduce", limit=None, created=NOW - timedelta(days=60), days=30, tz=NY):
    return compute_stats(
        goal=goal,
        daily_limit=limit,
        created_at=created,
        entries=list(entries),
        days=days,
        tz=tz,
        now=NOW,
    )


def test_buckets_by_local_day_not_utc():
    # 02:00 UTC June 15 is 22:00 June 14 in New York.
    stats = run([use(datetime(2026, 6, 15, 2, tzinfo=UTC))])
    by_date = {d["date"]: d["amount"] for d in stats["daily"]}
    assert by_date["2026-06-14"] == 1
    assert by_date["2026-06-15"] == 0


def test_same_instant_lands_on_different_day_in_other_zone():
    stats = run([use(datetime(2026, 6, 15, 2, tzinfo=UTC))], tz=ZoneInfo("Europe/Paris"))
    by_date = {d["date"]: d["amount"] for d in stats["daily"]}
    assert by_date["2026-06-15"] == 1


def test_dst_days_have_correct_length():
    start, end = day_bounds(datetime(2026, 3, 8).date(), NY)
    assert (end.astimezone(UTC) - start.astimezone(UTC)) == timedelta(hours=23)
    start, end = day_bounds(datetime(2026, 11, 1).date(), NY)
    assert (end.astimezone(UTC) - start.astimezone(UTC)) == timedelta(hours=25)


def test_days_before_tracking_are_not_counted_as_zero():
    stats = run(created=NOW - timedelta(days=2))
    assert len(stats["daily"]) == 3
    assert stats["window_start"] == "2026-06-13"


def test_backdated_entry_extends_history_to_before_creation():
    stats = run([use(NOW - timedelta(days=5))], created=NOW)
    assert stats["window_start"] == "2026-06-10"


def test_window_is_capped_to_requested_days():
    stats = run(days=7)
    assert len(stats["daily"]) == 7
    assert stats["daily"][-1]["date"] == "2026-06-15"


def test_moving_average_uses_only_tracked_days():
    created = NOW - timedelta(days=1)
    stats = run([use(NOW - timedelta(days=1), 4.0)], created=created)
    assert stats["daily"][0]["average_7d"] == 4
    assert stats["daily"][1]["average_7d"] == 2


def test_moving_average_reaches_outside_visible_window():
    entries = [use(NOW - timedelta(days=8), 7.0)]
    stats = run(entries, days=7)
    # June 9 is the first visible day; its 7-day span runs June 3 to 9. June 7 is the only day
    # accounted for, so blank days don't dilute the average.
    assert stats["daily"][0]["date"] == "2026-06-09"
    assert stats["daily"][0]["average_7d"] == 7


def test_week_comparison_ignores_partial_today():
    entries = [use(NOW - timedelta(days=d)) for d in range(1, 8)]  # 7 in the last full week
    entries += [use(NOW - timedelta(days=d), 2.0) for d in range(8, 15)]  # 14 the week before
    entries += [use(NOW, 50.0)]  # today, excluded
    summary = run(entries)["summary"]
    assert summary["recent_7"] == 7 and summary["previous_7"] == 14
    assert summary["change_pct"] == -50


def test_week_comparison_absent_without_enough_history():
    summary = run(created=NOW - timedelta(days=10))["summary"]
    assert summary["recent_7"] == 0
    assert summary["previous_7"] is None and summary["change_pct"] is None


def test_no_percent_when_a_compared_week_has_blank_days():
    entries = [use(NOW - timedelta(days=d)) for d in range(2, 15)]
    assert run(entries)["summary"]["change_pct"] is None


def test_no_percent_when_previous_week_was_zero():
    summary = run([use(NOW - timedelta(days=2))])["summary"]
    assert summary["previous_7"] == 0 and summary["change_pct"] is None


def test_within_goal_counts_finished_days_against_limit():
    created = NOW - timedelta(days=3)
    entries = [use(NOW - timedelta(days=1), 3.0), use(NOW - timedelta(days=2), 2.0), use(NOW, 9.0)]
    within = run(entries, limit=2, created=created)["summary"]["within_goal"]
    assert within == {"days": 1, "of": 2, "limit": 2}  # the blank day isn't counted


def test_quit_goal_treats_any_use_as_outside_goal():
    created = NOW - timedelta(days=2)
    within = run([use(NOW - timedelta(days=1))], goal="quit", created=created)["summary"][
        "within_goal"
    ]
    assert within == {"days": 0, "of": 1, "limit": 0}


def test_no_goal_figure_without_a_limit():
    assert run()["summary"]["within_goal"] is None


def test_urges_never_add_to_amounts_or_heatmap():
    stats = run([EntryRow("urge", NOW - timedelta(hours=1), None, craving=8, trigger="Stress")])
    assert stats["summary"]["amount_in_window"] == 0
    assert stats["summary"]["urges_in_window"] == 1
    assert stats["summary"]["average_craving"] == 8
    assert stats["summary"]["last_use_at"] is None
    assert sum(map(sum, stats["heatmap"])) == 0
    assert stats["triggers"] == [{"trigger": "Stress", "uses": 0, "urges": 1}]


def test_heatmap_uses_local_weekday_and_hour():
    # 01:30 UTC Monday June 15 is 21:30 Sunday June 14 in New York.
    stats = run([use(datetime(2026, 6, 15, 1, 30, tzinfo=UTC))])
    assert stats["heatmap"][6][21] == 1


def test_longest_gap_includes_time_since_last_use():
    entries = [use(NOW - timedelta(hours=30)), use(NOW - timedelta(hours=20))]
    created = NOW - timedelta(hours=31)
    assert run(entries, created=created)["summary"]["longest_gap_hours"] == 20


def test_longest_gap_counts_from_tracking_start_when_days_are_confirmed():
    created = NOW - timedelta(days=30)
    days = [(NOW - timedelta(days=d)).astimezone(NY).date() for d in range(1, 31)]
    result = compute_stats(
        goal="reduce",
        daily_limit=None,
        created_at=created,
        entries=[],
        days=30,
        tz=NY,
        now=NOW,
        confirmed_days=days,
    )
    assert result["summary"]["longest_gap_hours"] == 720


def test_blank_days_never_make_a_stretch():
    assert run(created=NOW - timedelta(days=30))["summary"]["longest_gap_hours"] == 0


def test_one_old_backdated_entry_cannot_flatter_goal_or_gap():
    created = NOW - timedelta(days=3)
    entries = [use(NOW - timedelta(days=d), 5.0) for d in range(0, 4)]
    entries.append(use(NOW - timedelta(days=300)))
    stats = run(entries, limit=2, created=created, days=365)
    summary = stats["summary"]
    assert summary["within_goal"] == {"days": 0, "of": 3, "limit": 2}
    assert summary["longest_gap_hours"] < 25
    assert stats["daily"][-1]["average_7d"] == 5
    assert stats["window_start"] == "2025-08-19"  # still visible on the chart


def test_empty_tracker_is_safe():
    summary = run()["summary"]
    assert summary["uses_in_window"] == 0
    assert summary["longest_gap_hours"] == 0 and summary["average_craving"] is None
