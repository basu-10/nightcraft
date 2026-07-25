"""Tests for app-admin telemetry dashboard."""
from unittest.mock import patch

from adminportal import create_app


def _client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_admin_root_renders_handoff():
    client = _client()
    response = client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Admin Panel" in html
    assert "Login with Shared Auth" in html


def test_telemetry_dashboard_prompts_login_when_not_admin():
    client = _client()
    response = client.get("/admin/telemetry")
    assert response.status_code == 302


def test_telemetry_dashboard_renders_for_admin():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("adminportal.fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}):
        client = app.test_client()
        response = client.get("/admin/telemetry")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Telemetry Dashboard" in html


def test_telemetry_summary_api_returns_error_without_db():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("adminportal.fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}):
        client = app.test_client()
        response = client.get("/admin/telemetry/api/summary")

    assert response.status_code == 500
    body = response.get_json()
    assert "error" in body


def test_telemetry_dashboard_blocks_non_admin():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("adminportal.fetch_shared_auth_user", return_value={"username": "regular_user", "is_admin": False}):
        client = app.test_client()
        response = client.get("/admin/telemetry")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
