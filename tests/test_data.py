import csv
import io
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.models import Base
from tests.conftest import PASSWORD


def second_user(client) -> TestClient:
    other = TestClient(client.app, base_url="http://testserver")
    res = other.post("/api/auth/register", json={"username": "bo-b", "password": PASSWORD})
    assert res.status_code == 201
    return other


def test_one_tap_log_uses_tracker_default(authed, tracker):
    entry = authed.post("/api/entries", json={"tracker_id": tracker["id"]}).json()
    assert entry["kind"] == "use" and entry["amount"] == 1
    day = authed.get("/api/today").json()[0]
    assert day["uses_today"] == 1 and day["amount_today"] == 1 and day["last_use_at"]


def test_urge_has_no_amount_and_cannot_gain_one(authed, tracker):
    entry = authed.post(
        "/api/entries", json={"tracker_id": tracker["id"], "kind": "urge", "amount": 5}
    ).json()
    assert entry["amount"] is None
    assert authed.patch(f"/api/entries/{entry['id']}", json={"amount": 2}).status_code == 422
    day = authed.get("/api/today").json()[0]
    assert day["uses_today"] == 0 and day["urges_today"] == 1 and day["last_use_at"] is None


def test_edit_details_and_clear_optional_fields(authed, tracker):
    entry = authed.post("/api/entries", json={"tracker_id": tracker["id"]}).json()
    url = f"/api/entries/{entry['id']}"
    res = authed.patch(url, json={"amount": 2.5, "craving": 7, "trigger": "Stress", "note": "hm"})
    assert res.json()["amount"] == 2.5 and res.json()["craving"] == 7
    res = authed.patch(url, json={"craving": 0, "trigger": "", "note": None})
    assert res.json()["craving"] == 0
    assert res.json()["trigger"] is None and res.json()["note"] is None
    assert res.json()["amount"] == 2.5
    assert authed.patch(url, json={"amount": None}).status_code == 422
    assert authed.patch(url, json={"craving": 11}).status_code == 422


def test_entry_time_rules(authed, tracker):
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    body = {"tracker_id": tracker["id"], "occurred_at": future}
    assert authed.post("/api/entries", json=body).status_code == 422
    body["occurred_at"] = "2026-01-01T10:00:00"  # no offset is ambiguous
    assert authed.post("/api/entries", json=body).status_code == 422
    body["occurred_at"] = "2026-01-01T10:00:00+02:00"
    res = authed.post("/api/entries", json=body)
    assert res.status_code == 201
    stored = authed.get("/api/entries").json()[0]["occurred_at"]
    assert datetime.fromisoformat(stored) == datetime(2026, 1, 1, 8, tzinfo=UTC)


def test_today_uses_the_local_midnight_of_the_requested_zone(authed, tracker):
    zone = ZoneInfo("Pacific/Auckland")
    midnight = datetime.now(zone).replace(hour=0, minute=0, second=0, microsecond=0)
    for offset, note in ((-1, "yesterday"), (1, "today")):
        when = (midnight + timedelta(minutes=offset)).isoformat()
        body = {"tracker_id": tracker["id"], "occurred_at": when, "note": note}
        assert authed.post("/api/entries", json=body).status_code == 201
    day = authed.get("/api/today", params={"tz": "Pacific/Auckland"}).json()[0]
    assert day["uses_today"] == 1


def test_implausibly_old_dates_are_refused(authed, tracker):
    for when in ("0001-01-01T00:00:00Z", "0001-01-01T00:00:00+14:00", "1999-12-31T00:00:00Z"):
        body = {"tracker_id": tracker["id"], "occurred_at": when}
        assert authed.post("/api/entries", json=body).status_code == 422
    entry = authed.post("/api/entries", json={"tracker_id": tracker["id"]}).json()
    res = authed.patch(f"/api/entries/{entry['id']}", json={"occurred_at": "0001-01-01T00:00:00Z"})
    assert res.status_code == 422


def test_bad_input_gets_a_client_error_not_a_crash(authed, tracker):
    huge = 2**70
    assert authed.get(f"/api/trackers/{huge}/stats").status_code == 422
    assert authed.get("/api/entries", params={"offset": huge}).status_code == 422
    assert authed.post("/api/entries", json={"tracker_id": huge}).status_code == 422
    res = authed.post(
        "/api/entries",
        content=b'{"tracker_id": %d, "note": "\\ud800"}' % tracker["id"],
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
    assert authed.get("/a%00b").status_code in (200, 503)


def test_null_archived_changes_nothing(authed, tracker):
    url = f"/api/trackers/{tracker['id']}"
    authed.patch(url, json={"archived": True})
    assert authed.patch(url, json={"archived": None}).json()["archived_at"] is not None


def test_invalid_time_zones_rejected(authed):
    for zone in ("Not/AZone", "../../etc/passwd", "America"):
        assert authed.get("/api/today", params={"tz": zone}).status_code == 422


def test_users_cannot_touch_each_others_data(authed, tracker):
    entry = authed.post(
        "/api/entries", json={"tracker_id": tracker["id"], "note": "private"}
    ).json()
    other = second_user(authed)
    tid, eid = tracker["id"], entry["id"]
    assert other.get("/api/trackers").json() == []
    assert other.get("/api/today").json() == []
    assert other.get("/api/entries").json() == []
    assert other.get("/api/entries", params={"tracker_id": tid}).json() == []
    assert other.get(f"/api/trackers/{tid}/stats").status_code == 404
    assert other.patch(f"/api/trackers/{tid}", json={"name": "x"}).status_code == 404
    assert other.delete(f"/api/trackers/{tid}").status_code == 404
    assert other.post("/api/entries", json={"tracker_id": tid}).status_code == 404
    assert other.patch(f"/api/entries/{eid}", json={"note": "x"}).status_code == 404
    assert other.delete(f"/api/entries/{eid}").status_code == 404
    assert "private" not in other.get("/api/export.csv").text
    assert "private" not in other.get("/api/export.json").text


def test_quit_goal_clears_limit(authed, tracker):
    res = authed.patch(f"/api/trackers/{tracker['id']}", json={"goal": "quit"})
    assert res.json()["daily_limit"] is None
    made = authed.post("/api/trackers", json={"name": "Dice", "goal": "quit", "daily_limit": 3})
    assert made.json()["daily_limit"] is None


def test_archive_hides_from_today_and_restore_returns(authed, tracker):
    url = f"/api/trackers/{tracker['id']}"
    authed.patch(url, json={"archived": True})
    assert authed.get("/api/today").json() == []
    assert authed.get("/api/trackers").json() == []
    assert len(authed.get("/api/trackers", params={"include_archived": True}).json()) == 1
    authed.patch(url, json={"archived": False})
    assert len(authed.get("/api/today").json()) == 1


def test_delete_tracker_removes_entries(authed, tracker):
    authed.post("/api/entries", json={"tracker_id": tracker["id"]})
    assert authed.delete(f"/api/trackers/{tracker['id']}").status_code == 204
    assert authed.get("/api/entries").json() == []


def test_entries_are_newest_first_and_paginated(authed, tracker):
    now = datetime.now(UTC)
    for hours in (3, 1, 2):
        when = (now - timedelta(hours=hours)).isoformat()
        authed.post(
            "/api/entries",
            json={"tracker_id": tracker["id"], "occurred_at": when, "note": str(hours)},
        )
    notes = [e["note"] for e in authed.get("/api/entries").json()]
    assert notes == ["1", "2", "3"]
    page = authed.get("/api/entries", params={"limit": 1, "offset": 1}).json()
    assert [e["note"] for e in page] == ["2"]


def test_export_csv_neutralises_spreadsheet_formulas(authed, tracker):
    authed.post(
        "/api/entries",
        json={"tracker_id": tracker["id"], "note": '=HYPERLINK("http://evil","x")'},
    )
    res = authed.get("/api/export.csv")
    assert "attachment" in res.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(res.text)))
    assert rows[0]["note"].startswith("'=")
    assert rows[0]["tracker"] == "Beer"


def test_export_json_round_trips_everything(authed, tracker):
    authed.post("/api/entries", json={"tracker_id": tracker["id"], "note": "n"})
    data = authed.get("/api/export.json").json()
    assert data["trackers"][0]["name"] == "Beer"
    assert data["entries"][0]["note"] == "n"


def test_unknown_api_path_is_404_not_html(client):
    assert client.get("/api/nope").status_code == 404


def test_static_serving_blocks_traversal(tmp_path):
    from tests.conftest import build_client

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>app</h1>")
    (tmp_path / "secret.txt").write_text("secret")
    client = build_client(tmp_path)
    assert "app" in client.get("/trends").text
    assert "secret" not in client.get("/..%2Fsecret.txt").text
    assert "secret" not in client.get("/%2e%2e/secret.txt").text


def test_migrations_match_models(client):
    engine = client.app.state.sessionmaker.kw["bind"]
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []
        assert {"users", "sessions", "trackers", "entries"} <= set(
            inspect(connection).get_table_names()
        )
