import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PASSWORD = "correct horse battery"


def build_client(tmp_path, **overrides) -> TestClient:
    settings = Settings(
        db_path=tmp_path / "test.db",
        signup=overrides.pop("signup", "open"),
        frontend_dist=tmp_path / "dist",
        **overrides,
    )
    return TestClient(create_app(settings), base_url="http://testserver")


@pytest.fixture
def client(tmp_path):
    return build_client(tmp_path)


@pytest.fixture
def authed(client):
    assert (
        client.post("/api/auth/register", json={"username": "ana", "password": PASSWORD})
    ).status_code == 201
    return client


@pytest.fixture
def tracker(authed):
    res = authed.post(
        "/api/trackers",
        json={"name": "Beer", "category": "alcohol", "unit": "drink", "daily_limit": 2},
    )
    assert res.status_code == 201
    return res.json()
