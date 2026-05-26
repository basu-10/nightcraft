import pytest


@pytest.mark.integration
def test_ui_login_page_available(client):
    rv = client.get("/ui/login")
    assert rv.status_code == 200
    assert b"Sign in to SeekSage" in rv.data


@pytest.mark.integration
def test_root_redirects_to_flask_ui(client):
    rv = client.get("/")
    assert rv.status_code == 302
    assert "/ui" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_dashboard_requires_auth(client):
    rv = client.get("/ui/dashboard")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_dashboard_for_authenticated_user(auth_client):
    rv = auth_client.get("/ui/dashboard")
    assert rv.status_code == 200
    assert b"Dashboard" in rv.data


@pytest.mark.integration
def test_ui_notes_requires_auth(client):
    rv = client.get("/ui/notes")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_notes_for_authenticated_user(auth_client):
    rv = auth_client.get("/ui/notes")
    assert rv.status_code == 200
    assert b"Create Note" in rv.data


@pytest.mark.integration
def test_ui_notifications_requires_auth(client):
    rv = client.get("/ui/notifications")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_notifications_for_authenticated_user(auth_client):
    rv = auth_client.get("/ui/notifications")
    assert rv.status_code == 200
    assert b"Loading notifications" in rv.data


@pytest.mark.integration
def test_ui_account_requires_auth(client):
    rv = client.get("/ui/account")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_account_for_authenticated_user(auth_client):
    rv = auth_client.get("/ui/account")
    assert rv.status_code == 200
    assert b"Change Password" in rv.data


@pytest.mark.integration
def test_ui_global_settings_requires_auth(client):
    rv = client.get("/ui/global-settings")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_global_settings_for_authenticated_user(auth_client):
    rv = auth_client.get("/ui/global-settings")
    assert rv.status_code == 200
    assert b"Provider Presets" in rv.data


@pytest.mark.integration
def test_ui_admin_requires_auth(client):
    rv = client.get("/ui/admin")
    assert rv.status_code == 302
    assert "/ui/login" in rv.headers.get("Location", "")


@pytest.mark.integration
def test_ui_admin_for_authenticated_admin(auth_client):
    rv = auth_client.get("/ui/admin")
    assert rv.status_code == 200
    assert b"Create User" in rv.data
