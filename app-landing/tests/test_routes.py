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
    assert "NEERA" in html
    assert "SeekSage" in html
    assert "NoteStack" in html
    assert "Sign In" in html
    assert "Sign Up" in html
    assert '/auth/login?next=%2F' in html
    assert 'href="/seeksage/ui"' in html
    assert 'href="/notestack/app"' in html


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
    assert "Open SeekSage Admin" in html
    assert "Open NoteStack Admin" in html


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
