import pytest


@pytest.mark.integration
def test_ui_login_page_available(client):
    rv = client.get("/ui/login")
    assert rv.status_code == 200
    assert b"Sign in to SeekSage" in rv.data


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
