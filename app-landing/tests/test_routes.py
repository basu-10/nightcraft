"""Integration tests for landing routes."""
from unittest.mock import patch

from landing import create_app


def _client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_root_route_renders_product_cards_and_links():
    client = _client()

    response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "DevRadio" in html
    assert "Butler" in html
    assert "NoteStack" in html
    assert "Sign In" in html
    assert "Sign Up" in html
    assert '/auth/login?next=%2F' in html
    assert 'href="/notestack/app"' in html
    assert 'href="/butler"' in html
    assert 'href="/experimental"' in html
    assert "SeekSage" not in html
    assert "NEERA" not in html


def test_root_route_admin_link_uses_platform_admin_path_for_admin_user():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}):
        client = app.test_client()
        response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'href="/platform-admin"' in html


def test_root_route_shows_welcome_and_logout_when_shared_auth_is_present():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}):
        client = app.test_client()
        response = client.get("/")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Hi, seedadmin welcome" in html
    assert "Sign Out" in html
    assert "Sign Up" not in html
    assert "Admin Dashboard" in html


def test_healthz_route_returns_expected_payload():
    client = _client()

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "landing"}


def test_admin_route_prompts_login_when_not_authenticated():
    client = _client()

    response = client.get("/platform-admin")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Platform Admin Dashboard" in html
    assert "Sign in to access admin controls" in html
    assert "Unified Login" in html
    assert "Admin Login" in html
    assert "Open Neera Admin" not in html


def test_admin_route_renders_admin_cards_for_admin_user():
    app = create_app()
    app.config.update(TESTING=True)

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}):
        client = app.test_client()
        response = client.get("/platform-admin")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Hi, seedadmin welcome" in html
    assert "Open DevRadio Admin" in html
    assert "Open Neera Admin" in html
    assert "Open NoteStack Admin" in html
    assert "Open SeekSage Admin" not in html


def test_experimental_route_renders_sections_and_apps():
    client = _client()

    response = client.get("/experimental")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sometimes life is better with a little less complexity" in html
    assert "For the love of the Tech, People, Nature and more" in html
    assert "TinyXL" in html
    assert "TexTrace" in html
    assert "Lazy Games" in html
    assert "ScrapBook" in html
    assert "MioBook" in html
    assert "Neera" in html
    assert "(proof of concept only / local accounts only)" in html
    assert "SeekSage" not in html


def test_platform_admin_alias_route_still_works_for_local_usage():
    client = _client()

    response = client.get("/admin")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Platform Admin Dashboard" in html


def test_legacy_curio_route_redirects_to_neera():
    client = _client()

    response = client.get("/curio", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"] == "/neera"


def test_platform_admin_users_prompts_login_when_not_admin():
    client = _client()

    response = client.get("/platform-admin/users")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Platform Users" in html
    assert "Sign in with an admin account" in html
    assert "user-search" not in html


def test_platform_admin_users_lists_users_for_admin():
    app = create_app()
    app.config.update(TESTING=True)

    sample_payload = {
        "users": [
            {"id": 1, "username": "seedadmin", "email": "admin@example.com", "is_admin": True, "active_sessions": 2, "created_at": "2026-01-01T00:00:00+00:00"},
            {"id": 2, "username": "seeduser", "email": "user@example.com", "is_admin": False, "active_sessions": 0, "created_at": "2026-01-02T00:00:00+00:00"},
        ],
        "total": 2,
        "page": 1,
        "pages": 1,
    }

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}), \
         patch("landing.routes._call_auth_admin", return_value=(200, sample_payload)):
        client = app.test_client()
        response = client.get("/platform-admin/users")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "seedadmin" in html
    assert "seeduser" in html
    assert "2 users total" in html


def test_platform_admin_logs_renders_for_admin():
    app = create_app()
    app.config.update(TESTING=True)

    sample_payload = {
        "activity": [
            {"kind": "session", "timestamp": "2026-01-01T00:00:00+00:00", "username": "seedadmin", "detail": "Signed in"},
        ],
        "clients": [
            {"client_id": "radio-app", "scope": "openid profile email", "is_confidential": True, "created_at": "2026-01-01T00:00:00+00:00"},
        ],
        "stats": {"users": 2, "active_sessions": 1, "oauth_clients": 1},
    }

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}), \
         patch("landing.routes._call_auth_admin", return_value=(200, sample_payload)):
        client = app.test_client()
        response = client.get("/platform-admin/logs")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Activity" in html
    assert "radio-app" in html


def test_platform_admin_user_detail_renders_for_admin():
    app = create_app()
    app.config.update(TESTING=True)

    sample_payload = {
        "user": {"id": 2, "username": "seeduser", "email": "user@example.com", "is_admin": False, "active_sessions": 0, "created_at": "2026-01-02T00:00:00+00:00"},
        "sessions": [],
        "refresh_tokens": [],
        "authorization_codes": [],
    }

    with patch("landing.routes._fetch_shared_auth_user", return_value={"username": "seedadmin", "is_admin": True}), \
         patch("landing.routes._call_auth_admin", return_value=(200, sample_payload)):
        client = app.test_client()
        response = client.get("/platform-admin/users/2")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "seeduser" in html
    assert "Reset password" in html
