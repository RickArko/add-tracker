from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import AuthSession, User
from app.security import COOKIE_NAME, LoginThrottle
from tests.conftest import PASSWORD, build_client


def creds(username="ana", password=PASSWORD):
    return {"username": username, "password": password}


def test_register_login_logout_cycle(client):
    assert client.get("/api/trackers").status_code == 401
    assert client.post("/api/auth/register", json=creds()).status_code == 201
    assert client.get("/api/trackers").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/trackers").status_code == 401
    assert client.post("/api/auth/login", json=creds()).status_code == 200
    assert client.get("/api/auth/status").json()["user"]["username"] == "ana"


def test_session_cookie_flags_and_hashed_storage(tmp_path):
    client = build_client(tmp_path, secure_cookies=True)
    res = client.post("/api/auth/register", json=creds())
    header = res.headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=strict" in header and "secure" in header
    token = res.cookies.get(COOKIE_NAME)
    with client.app.state.sessionmaker() as db:
        assert db.scalars(select(AuthSession.token_hash)).one() != token
        assert PASSWORD not in db.scalars(select(User.password_hash)).one()


def test_first_mode_allows_only_one_account(tmp_path):
    client = build_client(tmp_path, signup="first")
    assert client.get("/api/auth/status").json()["signup_open"] is True
    assert client.post("/api/auth/register", json=creds()).status_code == 201
    assert client.get("/api/auth/status").json()["signup_open"] is False
    assert client.post("/api/auth/register", json=creds("bo")).status_code in (403, 422)
    assert client.post("/api/auth/register", json=creds("bob")).status_code == 403


def test_closed_mode(tmp_path):
    client = build_client(tmp_path, signup="closed")
    assert client.post("/api/auth/register", json=creds()).status_code == 403


def test_rejects_short_password_and_duplicate_username(client):
    assert client.post("/api/auth/register", json=creds(password="short")).status_code == 422
    assert client.post("/api/auth/register", json=creds()).status_code == 201
    client.post("/api/auth/logout")
    assert client.post("/api/auth/register", json=creds("ANA")).status_code == 409


def test_login_throttled_after_repeated_failures(client):
    client.post("/api/auth/register", json=creds())
    client.post("/api/auth/logout")
    for _ in range(5):
        assert client.post("/api/auth/login", json=creds(password="wrong")).status_code == 401
    assert client.post("/api/auth/login", json=creds()).status_code == 429


def test_throttle_window_expires():
    now = [0.0]
    throttle = LoginThrottle(limit=2, window=10, clock=lambda: now[0])
    assert throttle.reserve("a") and throttle.reserve("a")
    assert not throttle.reserve("a")
    now[0] = 11
    assert throttle.reserve("a")


def post_in_parallel(client, path, bodies):
    def send(body):
        return TestClient(client.app, base_url="http://testserver").post(path, json=body)

    with ThreadPoolExecutor(len(bodies)) as pool:
        return [r.status_code for r in pool.map(send, bodies)]


def test_parallel_guesses_cannot_beat_the_throttle(client):
    client.post("/api/auth/register", json=creds())
    codes = post_in_parallel(client, "/api/auth/login", [creds(password="wrong")] * 8)
    assert codes.count(401) == 5 and codes.count(429) == 3


def test_parallel_signups_cannot_all_be_first(tmp_path):
    client = build_client(tmp_path, signup="first")
    codes = post_in_parallel(client, "/api/auth/register", [creds(f"user{i}") for i in range(4)])
    assert codes.count(201) == 1 and codes.count(403) == 3


def test_change_password_signs_out_other_devices(client, tmp_path):
    client.post("/api/auth/register", json=creds())
    other = build_other_session(client)
    assert other.get("/api/trackers").status_code == 200
    bad = {"current_password": "nope", "new_password": "another good passphrase"}
    assert client.post("/api/auth/password", json=bad).status_code == 403
    good = {"current_password": PASSWORD, "new_password": "another good passphrase"}
    assert client.post("/api/auth/password", json=good).status_code == 200
    assert client.get("/api/trackers").status_code == 200
    assert other.get("/api/trackers").status_code == 401


def build_other_session(client):
    from fastapi.testclient import TestClient

    other = TestClient(client.app, base_url="http://testserver")
    assert other.post("/api/auth/login", json=creds()).status_code == 200
    return other


def test_delete_account_removes_everything(authed, tracker):
    authed.post("/api/entries", json={"tracker_id": tracker["id"]})
    res = authed.request("DELETE", "/api/auth/account", json={"password": "wrong-password"})
    assert res.status_code == 403
    res = authed.request("DELETE", "/api/auth/account", json={"password": PASSWORD})
    assert res.status_code == 204
    assert authed.get("/api/trackers").status_code == 401
    with authed.app.state.sessionmaker() as db:
        for table in ("users", "sessions", "trackers", "entries"):
            count = db.connection().exec_driver_sql(f"SELECT count(*) FROM {table}").scalar()  # noqa: S608
            assert count == 0, table


def test_cross_site_write_refused(authed):
    res = authed.post(
        "/api/trackers", json={"name": "x"}, headers={"Origin": "https://evil.example"}
    )
    assert res.status_code == 403
    res = authed.post("/api/trackers", json={"name": "x"}, headers={"Origin": "http://testserver"})
    assert res.status_code == 201


def test_security_headers(client):
    res = client.get("/api/auth/status")
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert res.headers["cache-control"] == "no-store"
    assert res.headers["referrer-policy"] == "no-referrer"
