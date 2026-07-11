import importlib
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _create_app(monkeypatch, tmp_path, *, auth_mode="local", auth_service_url="http://auth.example/auth"):
    db_path = tmp_path / "notestack.db"
    monkeypatch.setenv("NOTESTACK_DB", str(db_path))
    monkeypatch.setenv("NOTESTACK_DB_BACKEND", "sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_MODE", auth_mode)
    monkeypatch.setenv("AUTH_SERVICE_URL", auth_service_url)
    monkeypatch.setenv("FLASK_ENV", "development")

    import app as note_app

    importlib.reload(note_app)
    flask_app = note_app.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


def _register_admin(client):
    return client.post(
        "/auth/register",
        data={
            "username": "usage-admin",
            "email": "usage-admin@example.com",
            "password": "supersecret",
            "timezone": "UTC",
        },
    )


def test_usage_event_captured_for_guest_page_view(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    client.get("/")

    import app.database as database

    with app.app_context():
        result = database.get_usage_events(event_type="page_home")
    assert result["total"] >= 1
    assert result["events"][0]["user_id"] is None


def test_usage_auth_events_recorded(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)

    import app.database as database

    with app.app_context():
        result = database.get_usage_events(event_type="auth_register")
    assert result["total"] == 1
    assert result["events"][0]["user_id"] is not None


def test_usage_capture_on_api_note_create(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)

    import app.database as database

    with app.app_context():
        token = client.post("/auth/token", json={}).get_json()["token"]

    client.post(
        "/api/notes",
        json={"title": "Captured note"},
        headers={"Authorization": f"Bearer {token}"},
    )

    with app.app_context():
        result = database.get_usage_events(event_type="note_create")
    assert result["total"] == 1
    assert result["events"][0]["user_id"] is not None


def test_admin_can_view_usage_analytics(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)
    client.get("/")

    response = client.get("/admin/usage")
    assert response.status_code == 200
    assert b"Usage Analytics" in response.data


def test_admin_usage_export_csv_and_json(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)
    client.get("/")

    csv_resp = client.get("/admin/usage/export?format=csv")
    assert csv_resp.status_code == 200
    assert csv_resp.mimetype == "text/csv"
    assert b"event_type" in csv_resp.data

    json_resp = client.get("/admin/usage/export?format=json")
    assert json_resp.status_code == 200
    assert json_resp.mimetype == "application/json"
    assert isinstance(json_resp.get_json(), list)


def test_admin_can_delete_and_clear_usage_events(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)
    client.get("/")

    import app.database as database

    with app.app_context():
        before = database.get_usage_events()["total"]
        assert before >= 1
        first_id = database.get_usage_events(limit=1)["events"][0]["id"]

    del_resp = client.post(f"/admin/usage/events/{first_id}/delete")
    assert del_resp.status_code == 302

    with app.app_context():
        assert database.get_usage_event(first_id) is None
        remaining = database.get_usage_events()["total"]
        assert remaining == before - 1

    clear_resp = client.post("/admin/usage/clear")
    assert clear_resp.status_code == 302

    with app.app_context():
        assert database.get_usage_events()["total"] == 0


def test_admin_clear_respects_event_filter(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()
    _register_admin(client)
    client.get("/")
    client.get("/app")

    import app.database as database

    with app.app_context():
        assert database.get_usage_events(event_type="page_home")["total"] >= 1
        assert database.get_usage_events(event_type="page_app")["total"] >= 1

    # Clear only page_app events.
    resp = client.post("/admin/usage/clear", data={"event_type": "page_app"})
    assert resp.status_code == 302

    with app.app_context():
        assert database.get_usage_events(event_type="page_app")["total"] == 0
        assert database.get_usage_events(event_type="page_home")["total"] >= 1


def test_non_admin_cannot_view_usage(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    client = app.test_client()

    _register_admin(client)
    client.post(
        "/auth/register",
        data={
            "username": "regular-user",
            "email": "regular@example.com",
            "password": "supersecret",
            "timezone": "UTC",
        },
    )
    client.post(
        "/auth/login",
        data={"username": "regular-user", "password": "supersecret"},
    )

    response = client.get("/admin/usage", follow_redirects=False)
    assert response.status_code == 302
    assert "admin/usage" not in response.headers["Location"]
