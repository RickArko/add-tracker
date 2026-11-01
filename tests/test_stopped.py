from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.stats import EntryRow, compute_stats

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 11, 1, 16, 0, tzinfo=UTC)
TODAY = date(2026, 11, 1)
LAST_USE = date(2025, 9, 20)
CREATED = NOW - timedelta(hours=1)


def run(entries=(), *, stopped_on=LAST_USE, created=CREATED, days=30):
    return compute_stats(
        goal="quit",
        daily_limit=None,
        created_at=created,
        entries=list(entries),
        days=days,
        tz=NY,
        now=NOW,
        stopped_on=stopped_on,
    )


def use_on(day: date) -> EntryRow:
    return EntryRow("use", datetime(day.year, day.month, day.day, 12, tzinfo=NY), 1.0)


def test_counts_finished_days_since_the_last_use():
    # September 21 to October 31. November 1 counts once it's over.
    assert run()["game"]["stopped"] == {
        "since": "2025-09-20",
        "days_free": 406,
        "current_days": 406,
        "longest_days": 406,
        "days_with_use": 0,
        "urges": 0,
    }


def test_no_blank_day_prompts_or_unlogged_notes():
    result = run()
    assert result["game"]["unlogged_recent"] == []
    assert result["summary"]["unlogged_days"] == 0


def test_an_earlier_use_costs_that_day_and_keeps_the_longest_stretch():
    stopped = run([use_on(TODAY - timedelta(days=10))])["game"]["stopped"]
    assert stopped["days_free"] == 405
    assert stopped["current_days"] == 9
    assert stopped["longest_days"] == 396
    assert stopped["days_with_use"] == 1


def test_a_use_today_lowers_nothing_but_the_current_stretch():
    stopped = run([use_on(TODAY)])["game"]["stopped"]
    assert stopped["current_days"] == 0 and stopped["days_with_use"] == 1
    assert stopped["days_free"] == 406 and stopped["longest_days"] == 406


def test_a_use_today_cannot_take_back_a_milestone():
    # Exactly on a threshold: 365 finished days, where counting today would have lost one.
    last_use = TODAY - timedelta(days=366)
    before = run(stopped_on=last_use)["game"]["milestones"][0]
    after = run([use_on(TODAY)], stopped_on=last_use)["game"]["milestones"][0]
    assert before["value"] == 365 and before["earned"] == 8
    assert after == before


def test_milestones_run_past_the_regular_gap_ladder():
    milestones = run()["game"]["milestones"]
    assert [m["key"] for m in milestones] == ["stopped", "urges"]
    assert milestones[0]["next"] == 730


def test_uses_up_to_the_last_use_date_do_not_count_against_it():
    stopped = run([use_on(LAST_USE - timedelta(days=5)), use_on(LAST_USE)])["game"]["stopped"]
    assert stopped["days_free"] == 406 and stopped["days_with_use"] == 0


def test_only_urges_after_the_last_use_date_count():
    urge = EntryRow("urge", NOW - timedelta(days=1))
    earlier = EntryRow("urge", datetime(2025, 9, 1, 12, tzinfo=NY))
    game = run([urge, earlier])["game"]
    assert game["stopped"]["urges"] == 1
    assert game["milestones"][1]["value"] == 1


def test_days_tracked_before_stopping_are_not_asked_about():
    result = run(stopped_on=TODAY - timedelta(days=3), created=NOW - timedelta(days=10))
    assert result["game"]["stopped"]["days_free"] == 2
    assert result["game"]["unlogged_recent"] == []


def test_regular_trackers_are_unchanged():
    result = run(stopped_on=None, created=NOW - timedelta(days=5))
    assert result["game"]["stopped"] is None
    assert [m["key"] for m in result["game"]["milestones"]] == [
        "gap",
        "urges",
        "within",
        "logged",
    ]
    assert len(result["game"]["unlogged_recent"]) == 5


def _kratom(client: TestClient, **extra) -> dict:
    body = {"name": "Kratom", "category": "opioid", "goal": "quit", "unit": "dose"}
    response = client.post("/api/trackers", json=body | extra)
    assert response.status_code == 201, response.text
    return response.json()


def test_api_stores_and_reports_the_date(authed):
    client = authed
    tracker = _kratom(client, stopped_on="2025-09-20")
    assert tracker["stopped_on"] == "2025-09-20"
    today = client.get("/api/today").json()[0]
    assert today["game"]["stopped"]["since"] == "2025-09-20"
    assert today["game"]["stopped"]["days_free"] > 300
    exported = client.get("/api/export.json").json()
    assert exported["trackers"][0]["stopped_on"] == "2025-09-20"


def test_api_refuses_today_future_and_ancient_dates(authed):
    client = authed
    for bad in ("2999-01-01", "1990-01-01", datetime.now(UTC).date().isoformat()):
        body = {"name": "Kratom", "goal": "quit", "stopped_on": bad}
        assert client.post("/api/trackers", json=body).status_code == 422


def test_api_ignores_the_date_without_a_stop_goal(authed):
    client = authed
    assert _kratom(client, goal="reduce", stopped_on="2025-09-20")["stopped_on"] is None


def test_changing_the_goal_or_clearing_the_date_returns_to_regular_tracking(authed):
    client = authed
    tracker = _kratom(client, stopped_on="2025-09-20")
    url = f"/api/trackers/{tracker['id']}"
    assert client.patch(url, json={"name": "K"}).json()["stopped_on"] == "2025-09-20"
    assert client.patch(url, json={"goal": "reduce"}).json()["stopped_on"] is None
    client.patch(url, json={"goal": "quit", "stopped_on": "2025-09-20"})
    assert client.patch(url, json={"stopped_on": None}).json()["stopped_on"] is None
    assert client.get("/api/today").json()[0]["game"]["stopped"] is None


def test_saving_an_unchanged_date_is_never_refused(authed):
    # The date can become "today" after travelling west, and a rename must still work.
    tracker = _kratom(authed, stopped_on="2025-09-20")
    body = {"name": "K", "stopped_on": "2025-09-20"}
    assert authed.patch(f"/api/trackers/{tracker['id']}?tz=Pacific/Pago_Pago", json=body).is_success


def test_levels_and_a_last_use_date_cannot_be_combined(authed):
    client = authed
    plan = {"baseline_amount": 6, "step_amount": 1, "clear_days": 7}
    stopped = _kratom(client, category="other", stopped_on="2025-09-20")
    refused = client.put(f"/api/trackers/{stopped['id']}/plan", json=plan)
    assert refused.status_code == 422

    levels = _kratom(client, category="other", goal="reduce")
    url = f"/api/trackers/{levels['id']}"
    assert client.put(f"{url}/plan", json=plan).status_code == 200
    body = {"goal": "quit", "stopped_on": "2025-09-20"}
    assert client.patch(url, json=body).status_code == 422


def test_a_tracker_that_is_not_yours_cannot_be_marked_stopped(authed):
    assert authed.patch("/api/trackers/999", json={"stopped_on": "2025-09-20"}).status_code == 404
