"""Public deploy guards: Google sessions + project ownership, daily USD and run caps."""

import time

import pytest
from fastapi.testclient import TestClient

from glr import api, auth, db
from glr.config import settings


def _session(sub: str) -> tuple[dict, str]:
    user = db.upsert_google_user(sub, f"{sub}@example.com", sub, None)
    token = f"tok-{sub}"
    db.create_session(user["id"], auth._hash(token), 60)
    return user, token


@pytest.fixture
def google(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "test-client.apps.googleusercontent.com")
    monkeypatch.setattr(api, "missing_keys", lambda: [])


def test_signed_out_gets_401_and_empty_list(google):
    c = TestClient(api.app)
    assert c.get("/api/auth/me").json() == {"mode": "google", "google_client_id": settings.google_client_id,
                                            "user": None}
    assert c.get("/api/projects").json() == []
    assert c.post("/api/projects", json={"text": "an idea long enough"}).status_code == 401


def test_projects_are_private_to_their_owner(google):
    alice, ta = _session("alice")
    _, tb = _session("bob")
    pid = db.create_project("alice's idea", user_id=alice["id"])
    a = TestClient(api.app, cookies={auth.COOKIE: ta})
    b = TestClient(api.app, cookies={auth.COOKIE: tb})
    assert a.get("/api/auth/me").json()["user"]["email"] == "alice@example.com"
    assert a.get(f"/api/projects/{pid}").status_code == 200
    assert [p["id"] for p in a.get("/api/projects").json()] == [pid]
    assert b.get(f"/api/projects/{pid}").status_code == 404
    assert b.delete(f"/api/projects/{pid}").status_code == 404
    assert b.get("/api/projects").json() == []


def test_expired_or_logged_out_session(google):
    _, t = _session("carol")
    c = TestClient(api.app, cookies={auth.COOKIE: t})
    assert c.post("/api/auth/logout").json() == {"ok": True}
    assert TestClient(api.app, cookies={auth.COOKIE: t}).get("/api/auth/me").json()["user"] is None


def test_email_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "allowed_emails", "judge@nvidia.com, @nebius.com")
    assert auth.allowed("Judge@NVIDIA.com") and auth.allowed("a@nebius.com")
    assert not auth.allowed("someone@gmail.com")
    monkeypatch.setattr(settings, "allowed_emails", "")
    assert auth.allowed("someone@gmail.com")


def test_dev_mode_only_from_loopback(monkeypatch):
    monkeypatch.setattr(settings, "google_client_id", "")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8100")
    assert auth.mode() == "dev"
    assert TestClient(api.app).get("/api/auth/me").json()["user"] is None  # TestClient host is not loopback
    monkeypatch.setattr(settings, "public_base_url", "https://research.example.com")
    assert auth.mode() == "off"


def test_daily_usd_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_usd_per_day", 0.5)
    db.x("INSERT INTO trace (project_id, ts, agent, kind, title, cost_usd) VALUES ('t', ?, 'a', 'llm', 'x', 0.6)",
         (time.time(),))
    with pytest.raises(api.HTTPException) as e:
        api._daily_guard()
    assert e.value.status_code == 429
    monkeypatch.setattr(settings, "max_usd_per_day", 5)
    api._daily_guard()


def test_daily_run_cap(monkeypatch):
    monkeypatch.setattr(settings, "max_runs_per_day", 2)
    api._daily_guard(run=True)
    api._daily_guard(run=True)
    api._daily_guard()  # non-run calls don't count
    with pytest.raises(api.HTTPException):
        api._daily_guard(run=True)
