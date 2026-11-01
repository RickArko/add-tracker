from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.db import MIGRATIONS_DIR
from app.stats import EntryRow, PeriodRow, PlanRow, compute_stats

UTC_ZONE = ZoneInfo("UTC")
NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)
TODAY = date(2026, 6, 15)


def use(days_ago, amount=6.0):
    return EntryRow("use", NOW - timedelta(days=days_ago), amount)


def stats(
    entries=(), *, limit=90.0, goal="reduce", created_days=30, periods=(), plan=None, confirmed=None
):
    if confirmed is None:
        confirmed = [TODAY - timedelta(days=d) for d in range(1, created_days + 1)]
    return compute_stats(
        confirmed_days=confirmed,
        goal=goal,
        daily_limit=limit,
        created_at=NOW - timedelta(days=created_days),
        entries=list(entries),
        days=365,
        tz=UTC_ZONE,
        now=NOW,
        periods=periods,
        plan=plan,
    )


def plan(started_days=10, clear=7):
    return PlanRow(90.0, 6.0, clear, TODAY - timedelta(days=started_days))


def period(days_ago, limit, goal="reduce"):
    return PeriodRow(TODAY - timedelta(days=days_ago), goal, limit)


def test_lowering_a_limit_does_not_rewrite_past_days():
    entries = [use(5, 84.0), use(1, 84.0)]
    periods = [period(30, 90.0), period(3, 78.0)]
    result = stats(entries, limit=78.0, periods=periods)
    by_date = {d["date"]: d for d in result["daily"]}
    assert by_date["2026-06-10"]["limit"] == 90 and by_date["2026-06-14"]["limit"] == 78
    within = result["summary"]["within_goal"]
    assert within["of"] == 30 and within["days"] == 29  # only the recent 84 is over
    assert within["limit"] == 78


def test_switching_to_quit_only_affects_days_from_then_on():
    periods = [period(30, 90.0), period(2, None, goal="quit")]
    result = stats([use(5, 50.0), use(1, 6.0)], limit=None, goal="quit", periods=periods)
    within = result["summary"]["within_goal"]
    assert within == {"days": 29, "of": 30, "limit": 0.0}


def test_level_numbers_and_forecast():
    level = stats(limit=78.0, periods=[period(3, 78.0)], plan=plan())["game"]["level"]
    assert level["level"] == 3 and level["total_levels"] == 16
    assert level["next_limit"] == 72
    assert level["days_cleared"] == 3 and not level["ready"]
    # 4 more days here, then 12 more levels of 7 days each.
    assert level["zero_by"] == (TODAY + timedelta(days=4 + 12 * 7)).isoformat()


def test_days_cleared_add_up_and_a_hard_day_never_subtracts():
    entries = [use(2, 100.0)]
    level = stats(entries, periods=[period(8, 90.0)], plan=plan())["game"]["level"]
    assert level["days_cleared"] == 7 and level["ready"]


def test_today_does_not_count_until_it_is_finished():
    level = stats(periods=[period(0, 90.0)], plan=plan())["game"]["level"]
    assert level["days_cleared"] == 0


def test_banked_never_goes_down_on_a_day_over_the_baseline():
    entries = [use(2, 200.0), use(1, 60.0)]
    level = stats(entries, periods=[period(3, 90.0)], plan=plan(started_days=3))["game"]["level"]
    # Three days ago banks 90, the 200 day banks 0 rather than a negative, the 60 day banks 30.
    assert level["banked"] == 120


def test_zero_level():
    level = stats(limit=None, goal="quit", periods=[period(4, None, "quit")], plan=plan())["game"][
        "level"
    ]
    assert level["at_zero"] and level["level"] == 16
    assert level["days_cleared"] == 4 and level["zero_by"] is None and not level["ready"]


def test_records_and_typical_gap():
    entries = [use(d, 30.0) for d in range(1, 15)] + [use(4, 0.5)]
    game = stats(entries, created_days=14)["game"]
    assert game["records"]["lowest_week"]["amount"] == 7 * 30  # any week without the extra log
    assert game["records"]["lowest_day"]["amount"] == 30
    assert game["typical_gap_hours"] == pytest.approx(24, abs=1)


def test_trend_needs_two_weeks_then_fits_a_line():
    assert stats([use(1)], created_days=5)["game"]["trend"] is None
    entries = [use(d, 40.0 + d) for d in range(1, 29)]
    trend = stats(entries, created_days=28)["game"]["trend"]
    assert trend["per_week"] == pytest.approx(-7, abs=0.01)
    assert trend["zero_by"] is not None
    flat = [use(d, 40.0) for d in range(1, 29)]
    assert stats(flat, created_days=28)["game"]["trend"]["zero_by"] is None


def test_milestones_report_the_next_target():
    game = stats([EntryRow("urge", NOW - timedelta(days=1), None)], created_days=2)["game"]
    urges = next(m for m in game["milestones"] if m["key"] == "urges")
    assert urges["value"] == 1 and urges["earned"] == 1 and urges["next"] == 10


def test_not_logging_earns_nothing():
    level = stats(periods=[period(10, 90.0)], plan=plan(), confirmed=[])["game"]["level"]
    assert level["days_cleared"] == 0 and level["banked"] == 0
    game = stats(periods=[period(10, 90.0)], plan=plan(), confirmed=[])["game"]
    assert next(m for m in game["milestones"] if m["key"] == "within")["value"] == 0
    assert game["records"]["longest_gap_hours"] == 0
    assert len(game["unlogged_recent"]) == 7


def test_adding_a_forgotten_log_to_a_blank_day_cannot_lower_progress():
    kw = {"periods": [period(5, 90.0)], "plan": plan(started_days=5)}
    entries = [use(d, 60.0) for d in (1, 3, 4, 5)]
    before = stats(entries, confirmed=[], **kw)["game"]["level"]
    after = stats([*entries, use(2, 120.0)], confirmed=[], **kw)["game"]["level"]
    assert after["days_cleared"] == before["days_cleared"] == 4
    assert after["banked"] == before["banked"]


def test_plan_on_an_old_tracker_starts_from_zero_progress():
    level = stats(periods=[period(30, 90.0)], plan=plan(started_days=0))["game"]["level"]
    assert level["days_cleared"] == 0 and not level["ready"]


def test_partial_first_day_is_not_an_unbeatable_record():
    entries = [use(d, 50.0) for d in range(1, 10)]
    low = stats(entries, created_days=10)["game"]["records"]["lowest_day"]
    assert low["amount"] == 50


def test_a_limit_above_the_start_steps_back_to_the_start():
    level = stats(limit=100.0, periods=[period(3, 100.0)], plan=plan())["game"]["level"]
    assert level["level"] == 1 and level["next_limit"] == 90


# --- API ---


def age_tracker(client, tracker_id, days=1):
    """Moves a tracker back in time and confirms yesterday, so a level can be cleared in a test."""
    with client.app.state.sessionmaker() as db:
        c = db.connection()
        c.exec_driver_sql(
            "UPDATE trackers SET created_at = datetime(created_at, ?), "
            "plan_started_on = date(plan_started_on, ?) WHERE id = ?",
            (f"-{days + 1} days", f"-{days + 1} days", tracker_id),
        )
        c.exec_driver_sql(
            "UPDATE limit_periods SET starts_on = date(starts_on, ?) WHERE tracker_id = ?",
            (f"-{days + 1} days", tracker_id),
        )
        db.commit()
    yesterday = (datetime.now(UTC) - timedelta(days=1)).date().isoformat()
    res = client.post(f"/api/trackers/{tracker_id}/no-use-days", json={"day": yesterday})
    assert res.status_code == 204


@pytest.fixture
def zyn(authed):
    res = authed.post(
        "/api/trackers",
        json={
            "name": "Zyn",
            "category": "nicotine",
            "unit": "mg",
            "default_amount": 6,
            "daily_limit": 90,
        },
    )
    return res.json()


def test_plan_step_down_all_the_way_to_quit(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    body = {"baseline_amount": 12, "step_amount": 6, "clear_days": 1}
    made = authed.put(f"{url}/plan", json=body).json()
    assert made["daily_limit"] == 12 and made["goal"] == "reduce"
    assert authed.post(f"{url}/step-down").status_code == 422  # not cleared yet
    age_tracker(authed, zyn["id"])
    assert authed.post(f"{url}/step-down").json()["daily_limit"] == 6
    assert authed.post(f"{url}/step-down").status_code == 422  # a double tap can't drop two
    age_tracker(authed, zyn["id"])
    last = authed.post(f"{url}/step-down").json()
    assert last["goal"] == "quit" and last["daily_limit"] is None
    assert authed.post(f"{url}/step-down").status_code == 422
    assert authed.get("/api/today").json()[0]["game"]["level"]["at_zero"]


def test_no_use_days_are_finished_days_without_a_logged_use(authed, zyn):
    url = f"/api/trackers/{zyn['id']}/no-use-days"
    today = datetime.now(UTC).date()
    assert authed.post(url, json={"day": today.isoformat()}).status_code == 422
    yesterday = today - timedelta(days=1)
    noon = datetime(yesterday.year, yesterday.month, yesterday.day, 12, tzinfo=UTC)
    entry = {"tracker_id": zyn["id"], "occurred_at": noon.isoformat()}
    assert authed.post("/api/entries", json=entry).status_code == 201
    assert authed.post(url, json={"day": yesterday.isoformat()}).status_code == 422
    other_day = (today - timedelta(days=2)).isoformat()
    assert authed.post(url, json={"day": other_day}).status_code == 204
    assert authed.post(url, json={"day": other_day}).status_code == 204  # repeat is harmless


def test_undo_by_client_id_handles_a_lost_reply_and_stays_scoped(authed, zyn):
    body = {"tracker_id": zyn["id"], "client_id": "device-123456"}
    authed.post("/api/entries", json=body)
    other = TestClient(authed.app, base_url="http://testserver")
    other.post("/api/auth/register", json={"username": "bo-b", "password": "correct horse bat"})
    assert other.delete("/api/entries/by-client/device-123456").status_code == 204
    assert len(authed.get("/api/entries").json()) == 1
    assert authed.delete("/api/entries/by-client/device-123456").status_code == 204
    assert authed.get("/api/entries").json() == []
    assert authed.delete("/api/entries/by-client/device-123456").status_code == 204


def test_editing_a_plan_keeps_its_start(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    authed.put(f"{url}/plan", json={"baseline_amount": 90, "step_amount": 6})
    age_tracker(authed, zyn["id"], days=3)
    before = authed.get(url.replace(f"/{zyn['id']}", "")).json()[0]["plan_started_on"]
    after = authed.put(f"{url}/plan", json={"baseline_amount": 90, "step_amount": 3}).json()
    assert after["plan_started_on"] == before


def test_fixing_a_mistyped_limit_the_same_day_keeps_progress(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    age_tracker(authed, zyn["id"], days=3)
    authed.patch(url, json={"daily_limit": 900})
    authed.patch(url, json={"daily_limit": 90})
    history = authed.get("/api/export.json").json()["limit_history"]
    assert len(history) == 1 and history[0]["daily_limit"] == 90
    assert history[0]["starts_on"] < datetime.now(UTC).date().isoformat()


def test_plan_refused_where_tapering_needs_a_clinician(authed):
    for category in ("alcohol", "benzodiazepine", "opioid"):
        made = authed.post("/api/trackers", json={"name": "x", "category": category}).json()
        body = {"baseline_amount": 10, "step_amount": 1}
        res = authed.put(f"/api/trackers/{made['id']}/plan", json=body)
        assert res.status_code == 422, category


def test_moving_to_a_clinician_only_category_removes_the_plan(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    authed.put(f"{url}/plan", json={"baseline_amount": 90, "step_amount": 6})
    assert authed.patch(url, json={"category": "alcohol"}).json()["step_amount"] is None


def test_step_cannot_exceed_baseline_and_plan_is_removable(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    bad = {"baseline_amount": 5, "step_amount": 6}
    assert authed.put(f"{url}/plan", json=bad).status_code == 422
    authed.put(f"{url}/plan", json={"baseline_amount": 90, "step_amount": 6})
    assert authed.delete(f"{url}/plan").json()["step_amount"] is None
    assert authed.get("/api/today").json()[0]["game"]["level"] is None


def test_goal_change_with_same_limit_keeps_level_progress(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    authed.patch(url, json={"goal": "manage"})
    history = authed.get("/api/export.json").json()["limit_history"]
    assert len(history) == 1 and history[0]["goal"] == "manage"


def test_same_day_limit_changes_keep_one_period(authed, zyn):
    url = f"/api/trackers/{zyn['id']}"
    authed.patch(url, json={"daily_limit": 80})
    authed.patch(url, json={"daily_limit": 70})
    history = authed.get("/api/export.json").json()["limit_history"]
    assert [p["daily_limit"] for p in history] == [70]


def test_resending_a_log_does_not_count_it_twice(authed, zyn):
    body = {"tracker_id": zyn["id"], "client_id": "device-123456"}
    first = authed.post("/api/entries", json=body).json()
    second = authed.post("/api/entries", json=body).json()
    assert first["id"] == second["id"]
    assert authed.get("/api/today").json()[0]["uses_today"] == 1


def test_client_ids_are_scoped_per_tracker_and_owner(authed, zyn):
    other = TestClient(authed.app, base_url="http://testserver")
    other.post("/api/auth/register", json={"username": "bo-b", "password": "correct horse bat"})
    theirs = other.post("/api/trackers", json={"name": "y"}).json()
    body = {"client_id": "device-123456"}
    mine = authed.post("/api/entries", json={"tracker_id": zyn["id"], **body}).json()
    res = other.post("/api/entries", json={"tracker_id": theirs["id"], **body}).json()
    assert mine["id"] != res["id"] and res["tracker_id"] == theirs["id"]


def test_other_users_cannot_change_plans(authed, zyn):
    other = TestClient(authed.app, base_url="http://testserver")
    other.post("/api/auth/register", json={"username": "bo-b", "password": "correct horse bat"})
    url = f"/api/trackers/{zyn['id']}"
    body = {"baseline_amount": 90, "step_amount": 6}
    assert other.put(f"{url}/plan", json=body).status_code == 404
    assert other.post(f"{url}/step-down").status_code == 404
    assert other.delete(f"{url}/plan").status_code == 404
    day = {"day": "2026-01-01"}
    assert other.post(f"{url}/no-use-days", json=day).status_code == 404


def test_delete_tracker_removes_limit_history(authed, zyn):
    authed.delete(f"/api/trackers/{zyn['id']}")
    with authed.app.state.sessionmaker() as db:
        count = db.connection().exec_driver_sql("SELECT count(*) FROM limit_periods").scalar()
    assert count == 0


def test_upgrade_from_first_release_keeps_data(tmp_path):
    url = f"sqlite:///{tmp_path / 'old.db'}"
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    config.attributes["db_url"] = url
    command.upgrade(config, "0001")
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(text("INSERT INTO users VALUES (1,'a','h','2026-01-05 10:00:00.000000')"))
        c.execute(
            text(
                "INSERT INTO trackers (id,user_id,name,category,goal,unit,default_amount,"
                "daily_limit,created_at) VALUES (1,1,'Zyn','nicotine','reduce','mg',6,90,"
                "'2026-01-05 10:00:00.000000')"
            )
        )
        c.execute(
            text(
                "INSERT INTO entries (tracker_id,kind,occurred_at,amount) "
                "VALUES (1,'use','2026-01-06 10:00:00.000000',6)"
            )
        )
    command.upgrade(config, "heads")
    with engine.begin() as c:
        assert c.execute(text("SELECT count(*) FROM entries")).scalar() == 1
        row = c.execute(text("SELECT starts_on, goal, daily_limit FROM limit_periods")).one()
        assert tuple(row) == ("2026-01-05", "reduce", 90)
    engine.dispose()
    command.downgrade(config, "0001")
