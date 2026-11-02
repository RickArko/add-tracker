import csv
import io
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.stats import EntryRow, PeriodRow, compute_stats, standard_drinks

TZ = {"tz": "UTC"}
IPA = {"name": "IPA", "servings": 3, "serving_ml": 355, "abv": 6.5}
FLUTES = {"name": "Champagne", "servings": 2, "serving_ml": 150, "abv": 12}


@pytest.fixture
def wine(authed):
    res = authed.post(
        "/api/trackers",
        params=TZ,
        json={"name": "Alcohol", "category": "alcohol", "daily_limit": 2, "standard_drinks": True},
    )
    assert res.status_code == 201
    return res.json()


def log(client, tracker, drink, **extra):
    return client.post("/api/entries", json={"tracker_id": tracker["id"], "drink": drink, **extra})


def today(client, tracker):
    rows = client.get("/api/today", params=TZ).json()
    return next(t for t in rows if t["id"] == tracker["id"])


# frontend/src/lib/drinks.test.ts checks the same figures.
@pytest.mark.parametrize(
    ("servings", "ml", "abv", "expected"),
    [
        (1, 355, 5, 1.0),
        (3, 355, 6.5, 3.9),
        (2, 150, 12, 2.0),
        (1, 148, 12, 1.0),
        (1, 44, 40, 1.0),
        (1, 355, 0.5, 0.1),
        (1, 10, 0.1, 0.1),
        (1, 700, 100, 39.5),
    ],
)
def test_standard_drink_figures(servings, ml, abv, expected):
    assert standard_drinks(servings, ml, abv) == expected


def test_turning_on_sets_the_unit_and_leaves_the_limit(wine):
    assert wine["unit"] == "standard drink"
    assert wine["default_amount"] == 1
    assert wine["daily_limit"] == 2
    assert wine["standard_drinks_from"]


def test_only_alcohol_can_count_standard_drinks(authed, tracker):
    res = authed.post(
        "/api/trackers",
        params=TZ,
        json={"name": "Vape", "category": "nicotine", "standard_drinks": True},
    )
    assert res.status_code == 422
    url = f"/api/trackers/{tracker['id']}"
    assert authed.patch(url, params=TZ, json={"standard_drinks": True}).status_code == 200
    res = authed.patch(url, params=TZ, json={"category": "nicotine"})
    assert res.json()["standard_drinks_from"] is None


def test_an_existing_tracker_opts_in_without_changing_its_past(authed, tracker):
    old = authed.post("/api/entries", json={"tracker_id": tracker["id"]}).json()
    url = f"/api/trackers/{tracker['id']}"
    on = authed.patch(url, params=TZ, json={"standard_drinks": True}).json()
    assert (on["unit"], on["daily_limit"]) == ("standard drink", 2)
    entries = authed.get("/api/entries").json()
    assert [e["amount"] for e in entries] == [old["amount"]]
    assert authed.patch(url, params=TZ, json={"name": "Drinks"}).json()["standard_drinks_from"]
    assert (
        authed.patch(url, params=TZ, json={"standard_drinks": False}).json()["standard_drinks_from"]
        is None
    )


def test_a_drink_is_only_for_alcohol(authed):
    vape = authed.post("/api/trackers", json={"name": "Vape", "category": "nicotine"}).json()
    assert log(authed, vape, IPA).status_code == 422


def test_a_drink_queued_offline_survives_the_setting_being_turned_off(authed, wine):
    authed.patch(f"/api/trackers/{wine['id']}", params=TZ, json={"standard_drinks": False})
    res = log(authed, wine, IPA, client_id="abcdefgh")
    assert res.status_code == 201
    assert res.json()["amount"] == 3.9


def test_turning_off_never_leaves_the_unit_behind(authed, wine):
    url = f"/api/trackers/{wine['id']}"
    assert authed.patch(url, params=TZ, json={"standard_drinks": False}).json()["unit"] == "drink"
    authed.patch(url, params=TZ, json={"standard_drinks": True})
    assert authed.patch(url, params=TZ, json={"category": "nicotine"}).json()["unit"] == "time"


def test_a_drink_is_one_entry_with_its_details_and_marks_for_each_serving(authed, wine):
    entry = log(authed, wine, IPA).json()
    assert entry["amount"] == 3.9
    assert (entry["drink_name"], entry["servings"], entry["serving_ml"], entry["abv"]) == (
        "IPA",
        3,
        355,
        6.5,
    )
    row = today(authed, wine)
    assert (row["uses_today"], row["amount_today"]) == (3, 3.9)
    assert len(authed.get("/api/entries").json()) == 1


def test_a_plain_tap_still_counts_one_on_a_standard_drinks_tracker(authed, wine):
    authed.post("/api/entries", json={"tracker_id": wine["id"]})
    row = today(authed, wine)
    assert (row["uses_today"], row["amount_today"]) == (1, 1)


def test_limits_use_the_converted_amount(authed, wine):
    log(authed, wine, FLUTES)
    assert today(authed, wine)["amount_today"] == 2.0
    stats = authed.get(f"/api/trackers/{wine['id']}/stats", params=TZ).json()
    assert stats["daily"][-1]["amount"] == 2.0


def test_resending_a_lost_drink_counts_once(authed, wine):
    first = log(authed, wine, IPA, client_id="abcdefgh").json()
    again = log(authed, wine, IPA, client_id="abcdefgh").json()
    assert first["id"] == again["id"]
    assert today(authed, wine)["uses_today"] == 3


@pytest.mark.parametrize(
    "bad",
    [
        {**IPA, "abv": 0},
        {**IPA, "abv": 101},
        {**IPA, "servings": 0},
        {**IPA, "servings": 51},
        {**IPA, "serving_ml": 0},
        {**IPA, "name": " "},
    ],
)
def test_impossible_drinks_are_refused(authed, wine, bad):
    assert log(authed, wine, bad).status_code == 422


def test_a_drink_cant_be_an_urge_or_also_have_an_amount(authed, wine):
    assert log(authed, wine, IPA, kind="urge").status_code == 422
    assert log(authed, wine, IPA, amount=2).status_code == 422


def test_editing_a_drink_recalculates_it(authed, wine):
    entry = log(authed, wine, IPA).json()
    url = f"/api/entries/{entry['id']}"
    res = authed.patch(url, json={"drink": {**IPA, "servings": 1}}).json()
    assert (res["amount"], res["servings"]) == (1.3, 1)
    assert authed.patch(url, json={"drink": IPA, "amount": 2}).status_code == 422
    same = authed.patch(url, json={"amount": 1.3, "note": "ok"}).json()
    assert same["drink_name"] == "IPA"
    typed = authed.patch(url, json={"amount": 2}).json()
    assert (typed["amount"], typed["drink_name"], typed["servings"]) == (2, None, None)


def test_recent_drinks_are_distinct_and_newest_first(authed, wine):
    log(authed, wine, IPA)
    log(authed, wine, FLUTES)
    log(authed, wine, {**IPA, "servings": 1})
    recent = today(authed, wine)["recent_drinks"]
    assert [d["name"] for d in recent] == ["IPA", "Champagne"]
    assert recent[0] == {"name": "IPA", "serving_ml": 355, "abv": 6.5}


def test_recent_drinks_stop_at_five(authed, wine):
    for n in range(7):
        log(authed, wine, {**IPA, "name": f"Beer {n}"})
    assert len(today(authed, wine)["recent_drinks"]) == 5


def test_a_stopped_tracker_gets_no_drink_list(authed, wine):
    log(authed, wine, IPA)
    authed.patch(
        f"/api/trackers/{wine['id']}", params=TZ, json={"goal": "quit", "stopped_on": "2025-01-01"}
    )
    assert today(authed, wine)["recent_drinks"] == []


def test_exports_include_the_drink_and_neutralise_its_name(authed, wine):
    log(authed, wine, {**IPA, "name": "=cmd()"})
    rows = list(csv.DictReader(io.StringIO(authed.get("/api/export.csv").text)))
    assert (rows[0]["drink"], rows[0]["servings"], rows[0]["abv"]) == ("'=cmd()", "3", "6.5")
    assert list(rows[0])[:8] == [
        "occurred_at_utc",
        "tracker",
        "kind",
        "amount",
        "unit",
        "craving",
        "trigger",
        "note",
    ]
    entry = authed.get("/api/export.json").json()["entries"][0]
    assert entry["drink_name"] == "=cmd()"


def test_a_day_exactly_at_a_fractional_limit_counts_as_within_it():
    # 1.1 three times adds up to 3.3000000000000003 as a float.
    now = datetime(2026, 1, 10, 12, tzinfo=UTC)
    day = now - timedelta(days=1)
    start = now - timedelta(days=5)
    stats = compute_stats(
        goal="manage",
        daily_limit=3.3,
        created_at=start,
        entries=[EntryRow("use", day, 1.1) for _ in range(3)],
        days=7,
        tz=ZoneInfo("UTC"),
        now=now,
        periods=[PeriodRow(start.date(), "manage", 3.3)],
    )
    within = next(m for m in stats["game"]["milestones"] if m["key"] == "within")
    assert within["value"] == 1
