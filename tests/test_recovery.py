from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AuthToken, User
from app.security import normalize_recovery_code
from tests.conftest import PASSWORD

NEW = "a brand new passphrase"
EMAIL = "Someone@Example.com"


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send(self, to, subject, body):
        self.sent.append((to, subject, body))

    def token(self):
        body = self.sent[-1][2]
        return body.split("token=")[1].split()[0]


@pytest.fixture
def app_with_mail(tmp_path):
    settings = Settings(
        db_path=tmp_path / "t.db",
        signup="open",
        frontend_dist=tmp_path / "dist",
        public_url="https://example.test",
        email_pepper="pepper",
    )
    app = create_app(settings)
    app.state.mailer = FakeMailer()
    return app


@pytest.fixture
def mail_client(app_with_mail):
    client = TestClient(app_with_mail, base_url="http://testserver")
    res = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD})
    assert res.status_code == 201
    return client


def fresh(client):
    return TestClient(client.app, base_url="http://testserver")


def login(client, password=PASSWORD):
    return client.post("/api/auth/login", json={"username": "ana", "password": password})


def add_and_confirm(client):
    body = {"email": EMAIL, "password": PASSWORD}
    assert client.post("/api/auth/email", json=body).status_code == 202
    token = client.app.state.mailer.token()
    assert client.post("/api/auth/email/confirm", json={"token": token}).status_code == 200


def test_signup_returns_a_code_once_and_stores_only_a_hash(client):
    res = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD})
    code = res.json()["recovery_code"]
    assert len(code) == 24 and res.json()["has_recovery_code"]
    status = client.get("/api/auth/status").json()
    assert "recovery_code" not in status["user"]
    with client.app.state.sessionmaker() as db:
        assert code not in db.scalars(select(User.recovery_code_hash)).one()


def test_recovery_code_resets_passphrase_is_single_use_and_ends_sessions(client):
    code = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD}).json()[
        "recovery_code"
    ]
    other = fresh(client)
    assert login(other).status_code == 200
    body = {"username": "ANA", "recovery_code": code.lower().replace("-", " "), "new_password": NEW}
    visitor = fresh(client)
    res = visitor.post("/api/auth/recover", json=body)
    assert res.status_code == 200
    replacement = res.json()["recovery_code"]
    assert replacement != code
    assert visitor.get("/api/trackers").status_code == 200
    assert other.get("/api/trackers").status_code == 401
    assert client.get("/api/trackers").status_code == 401
    assert login(fresh(client)).status_code == 401
    assert login(fresh(client), NEW).status_code == 200
    assert fresh(client).post("/api/auth/recover", json=body).status_code == 401
    again = {"username": "ana", "recovery_code": replacement, "new_password": PASSWORD}
    assert fresh(client).post("/api/auth/recover", json=again).status_code == 200


def test_wrong_code_and_unknown_user_look_the_same_and_cannot_lock_out_the_owner(client):
    code = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD}).json()[
        "recovery_code"
    ]
    bad = {"username": "ana", "recovery_code": "AAAA-BBBB", "new_password": NEW}
    ghost = {**bad, "username": "ghost"}
    first = client.post("/api/auth/recover", json=bad)
    second = client.post("/api/auth/recover", json=ghost)
    assert first.status_code == second.status_code == 401
    assert first.json() == second.json()
    for _ in range(8):
        client.post("/api/auth/recover", json=bad)
    good = {**bad, "recovery_code": code}
    assert client.post("/api/auth/recover", json=good).status_code == 200


def test_new_code_needs_passphrase_and_replaces_the_old(client):
    old = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD}).json()[
        "recovery_code"
    ]
    wrong = {"password": "wrong passphrase"}
    assert client.post("/api/auth/recovery-code", json=wrong).status_code == 403
    assert client.post("/api/auth/recovery-code", json={"password": PASSWORD}).status_code == 200
    body = {"username": "ana", "recovery_code": old, "new_password": NEW}
    assert fresh(client).post("/api/auth/recover", json=body).status_code == 401


def test_code_normalising_forgives_lookalike_characters():
    assert normalize_recovery_code("abcd efgh") == "ABCD-EFGH"
    assert normalize_recovery_code("oOiL-1") == "0011-1"


def test_email_feature_is_absent_until_configured(authed):
    assert authed.get("/api/auth/status").json()["email_enabled"] is False
    body = {"email": EMAIL}
    assert authed.post("/api/auth/email/reset-request", json=body).status_code == 404


def test_email_is_stored_only_as_a_hash(mail_client):
    add_and_confirm(mail_client)
    assert mail_client.get("/api/auth/status").json()["user"]["has_email"] is True
    with mail_client.app.state.sessionmaker() as db:
        c = db.connection()
        for table in ("users", "auth_tokens", "sessions"):
            for row in c.exec_driver_sql(f"SELECT * FROM {table}").all():  # noqa: S608
                assert "example.com" not in str(row).lower()


def test_email_only_counts_after_confirming(mail_client):
    mail_client.post("/api/auth/email", json={"email": EMAIL, "password": PASSWORD})
    sent = len(mail_client.app.state.mailer.sent)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    assert len(mail_client.app.state.mailer.sent) == sent
    assert mail_client.get("/api/auth/status").json()["user"]["has_email"] is False


def test_adding_email_needs_the_passphrase(mail_client):
    body = {"email": EMAIL, "password": "wrong passphrase"}
    assert mail_client.post("/api/auth/email", json=body).status_code == 403
    assert mail_client.app.state.mailer.sent == []


def test_email_reset_flow_is_single_use_and_ends_sessions(mail_client):
    add_and_confirm(mail_client)
    visitor = fresh(mail_client)
    # Case and spacing in the address don't matter.
    assert (
        visitor.post(
            "/api/auth/email/reset-request", json={"email": "  someone@EXAMPLE.com "}
        ).status_code
        == 202
    )
    mailer = mail_client.app.state.mailer
    assert mailer.sent[-1][0] == "someone@example.com"
    assert "https://example.test/reset?token=" in mailer.sent[-1][2]
    token = mailer.token()
    body = {"token": token, "new_password": NEW}
    assert visitor.post("/api/auth/email/reset", json=body).status_code == 200
    assert visitor.get("/api/trackers").status_code == 200
    assert mail_client.get("/api/trackers").status_code == 401
    assert login(fresh(mail_client), NEW).status_code == 200
    assert visitor.post("/api/auth/email/reset", json=body).status_code == 400


def test_reset_request_reveals_nothing_about_unknown_addresses(mail_client):
    add_and_confirm(mail_client)
    mailer = mail_client.app.state.mailer
    sent = len(mailer.sent)
    known = mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    unknown = mail_client.post("/api/auth/email/reset-request", json={"email": "no@example.org"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(mailer.sent) == sent + 1


def test_tokens_cannot_cross_purposes_or_outlive_expiry(mail_client):
    mail_client.post("/api/auth/email", json={"email": EMAIL, "password": PASSWORD})
    token = mail_client.app.state.mailer.token()
    res = mail_client.post("/api/auth/email/reset", json={"token": token, "new_password": NEW})
    assert res.status_code == 400
    with mail_client.app.state.sessionmaker() as db:
        row = db.scalars(select(AuthToken)).first()
        if row is None:
            return
        db.connection().exec_driver_sql("UPDATE auth_tokens SET expires_at = '2000-01-01 00:00:00'")
        db.commit()
    assert mail_client.post("/api/auth/email/confirm", json={"token": token}).status_code == 400


def test_changing_passphrase_cancels_every_older_route_back_in(mail_client):
    """Someone who once knew the passphrase can't keep a way in after it changes."""
    code = mail_client.post("/api/auth/recovery-code", json={"password": PASSWORD}).json()[
        "recovery_code"
    ]
    add_and_confirm(mail_client)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    reset_token = mail_client.app.state.mailer.token()
    mail_client.post("/api/auth/email", json={"email": "attacker@evil.test", "password": PASSWORD})
    confirm_token = mail_client.app.state.mailer.token()

    change = {"current_password": PASSWORD, "new_password": NEW}
    res = mail_client.post("/api/auth/password", json=change)
    assert res.status_code == 200 and res.json()["recovery_code"] != code
    assert res.json()["has_email"] is False

    old = {"username": "ana", "recovery_code": code, "new_password": "attacker passphrase"}
    assert fresh(mail_client).post("/api/auth/recover", json=old).status_code == 401
    res = mail_client.post(
        "/api/auth/email/reset", json={"token": reset_token, "new_password": "attacker passphrase"}
    )
    assert res.status_code == 400
    assert (
        mail_client.post("/api/auth/email/confirm", json={"token": confirm_token}).status_code
        == 400
    )


def test_recovering_with_a_code_removes_an_email_someone_else_may_have_added(mail_client):
    code = mail_client.post("/api/auth/recovery-code", json={"password": PASSWORD}).json()[
        "recovery_code"
    ]
    add_and_confirm(mail_client)
    body = {"username": "ana", "recovery_code": code, "new_password": NEW}
    assert fresh(mail_client).post("/api/auth/recover", json=body).json()["has_email"] is False


def test_email_reset_cancels_an_older_recovery_code(mail_client):
    code = mail_client.post("/api/auth/recovery-code", json={"password": PASSWORD}).json()[
        "recovery_code"
    ]
    add_and_confirm(mail_client)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    body = {"token": mail_client.app.state.mailer.token(), "new_password": NEW}
    visitor = fresh(mail_client)
    res = visitor.post("/api/auth/email/reset", json=body)
    assert res.json()["has_email"] is True and res.json()["recovery_code"] != code
    old = {"username": "ana", "recovery_code": code, "new_password": "another new passphrase"}
    assert fresh(mail_client).post("/api/auth/recover", json=old).status_code == 401


def test_confirm_needs_the_owners_session(mail_client):
    mail_client.post("/api/auth/email", json={"email": EMAIL, "password": PASSWORD})
    token = mail_client.app.state.mailer.token()
    scanner = fresh(mail_client)
    assert scanner.post("/api/auth/email/confirm", json={"token": token}).status_code == 401
    other = fresh(mail_client)
    other.post("/api/auth/register", json={"username": "bob", "password": PASSWORD})
    assert other.post("/api/auth/email/confirm", json={"token": token}).status_code == 400
    assert mail_client.post("/api/auth/email/confirm", json={"token": token}).status_code == 200


def test_a_link_works_once_even_with_parallel_requests(mail_client):
    add_and_confirm(mail_client)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    body = {"token": mail_client.app.state.mailer.token(), "new_password": NEW}

    def send(_):
        return fresh(mail_client).post("/api/auth/email/reset", json=body).status_code

    with ThreadPoolExecutor(6) as pool:
        codes = list(pool.map(send, range(6)))
    assert codes.count(200) == 1 and codes.count(400) == 5


def test_a_recovery_code_works_once_even_with_parallel_requests(client):
    code = client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD}).json()[
        "recovery_code"
    ]
    body = {"username": "ana", "recovery_code": code, "new_password": NEW}

    def send(_):
        return fresh(client).post("/api/auth/recover", json=body).status_code

    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(send, range(4)))
    assert codes.count(200) == 1 and codes.count(401) == 3


def test_reset_budget_cannot_starve_signed_in_users_or_reveal_an_address(mail_client):
    add_and_confirm(mail_client)
    for _ in range(10):
        fresh(mail_client).post("/api/auth/email/reset-request", json={"email": EMAIL})
    other = fresh(mail_client)
    other.post("/api/auth/register", json={"username": "bob", "password": PASSWORD})
    # Spamming resets for this address doesn't change what adding it elsewhere reports.
    body = {"email": EMAIL, "password": PASSWORD}
    assert other.post("/api/auth/email", json=body).status_code == 202


def test_lookalike_characters_are_refused_and_case_is_normalised(mail_client):
    # A Kelvin sign would hash like a plain k while being a different address.
    body = {"email": "\u212aelly@example.com", "password": PASSWORD}
    assert mail_client.post("/api/auth/email", json=body).status_code == 422
    body["email"] = "KELLY@Example.com"
    assert mail_client.post("/api/auth/email", json=body).status_code == 202
    assert mail_client.app.state.mailer.sent[-1][0] == "kelly@example.com"


def test_odd_addresses_are_refused(mail_client):
    for bad in ("a,evil@b.cc", "\u00fcser@example.com", "a@b", "a b@c.de", "x\u0000y@b.cc"):
        res = mail_client.post("/api/auth/email/reset-request", json={"email": bad})
        assert res.status_code == 422, bad


def test_removing_email_stops_resets(mail_client):
    add_and_confirm(mail_client)
    res = mail_client.request("DELETE", "/api/auth/email", json={"password": PASSWORD})
    assert res.status_code == 204
    mailer = mail_client.app.state.mailer
    sent = len(mailer.sent)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    assert len(mailer.sent) == sent


def test_two_accounts_on_one_address_each_get_a_link(mail_client):
    add_and_confirm(mail_client)
    other = fresh(mail_client)
    other.post("/api/auth/register", json={"username": "bob", "password": PASSWORD})
    other.post("/api/auth/email", json={"email": EMAIL, "password": PASSWORD})
    other.post("/api/auth/email/confirm", json={"token": mail_client.app.state.mailer.token()})
    fresh(mail_client).post("/api/auth/email/reset-request", json={"email": EMAIL})
    body = mail_client.app.state.mailer.sent[-1][2]
    assert "ana: " in body and "bob: " in body


def test_mail_volume_is_capped_per_address(mail_client):
    add_and_confirm(mail_client)
    mailer = mail_client.app.state.mailer
    sent = len(mailer.sent)
    for _ in range(30):
        mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    assert len(mailer.sent) - sent == 3


def test_mail_never_mentions_substances_or_habits(mail_client):
    add_and_confirm(mail_client)
    mail_client.post("/api/auth/email/reset-request", json={"email": EMAIL})
    for _to, subject, body in mail_client.app.state.mailer.sent:
        text = (subject + body).lower().replace("https://example.test", "")
        for word in ("habit", "nicotine", "addiction", "substance", "tally"):
            assert word not in text
