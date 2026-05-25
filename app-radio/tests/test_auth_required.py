from urllib.parse import parse_qs, urlparse
import os

import pytest

from devradio import create_app
from devradio.extensions import db
from devradio.models import LocalCredential, UserProfile


def _build_test_app(tmp_path, auth_mode="local"):
    database_uri = os.getenv("TEST_DATABASE_URL")
    if not database_uri:
        pytest.skip("Set TEST_DATABASE_URL to run app-radio tests against PostgreSQL.")

    app = create_app(
        {
            "TESTING": True,
            "AUTH_MODE": auth_mode,
            "SQLALCHEMY_DATABASE_URI": database_uri,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def _assert_login_redirect(response):
    assert response.status_code in (301, 302, 303, 307, 308)
    target = response.headers.get("Location", "")
    parsed = urlparse(target)
    assert parsed.path == "/auth/login"
    next_values = parse_qs(parsed.query).get("next", [])
    assert next_values and next_values[0].startswith("/bookmarks")


def test_local_auth_required_redirects_unauthenticated(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="local")
    client = app.test_client()

    response = client.get("/bookmarks")
    _assert_login_redirect(response)


def test_local_homepage_shows_listener_and_admin_links(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="local")
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Listener Login" in page
    assert "Admin Login" in page


def test_local_auth_required_allows_authenticated_listener(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="local")
    with app.app_context():
        user = LocalCredential(username="listener1", role="listener")
        user.set_password("pw123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=str(user.id), username=user.username, is_admin=False))
        db.session.commit()

    client = app.test_client()
    login_response = client.post(
        "/auth/login",
        data={"username": "listener1", "password": "pw123"},
        follow_redirects=False,
    )
    assert login_response.status_code in (301, 302, 303)

    response = client.get("/bookmarks")
    assert response.status_code == 200


def test_local_admin_required_blocks_listener(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="local")
    with app.app_context():
        user = LocalCredential(username="listener2", role="listener")
        user.set_password("pw123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=str(user.id), username=user.username, is_admin=False))
        db.session.commit()

    client = app.test_client()
    login_response = client.post(
        "/auth/login",
        data={"username": "listener2", "password": "pw123"},
        follow_redirects=False,
    )
    assert login_response.status_code in (301, 302, 303)

    response = client.get("/admin/")
    assert response.status_code == 403


def test_local_admin_required_allows_admin(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="local")
    with app.app_context():
        user = LocalCredential(username="admin1", role="admin")
        user.set_password("pw123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserProfile(user_id=str(user.id), username=user.username, is_admin=True))
        db.session.commit()

    client = app.test_client()
    login_response = client.post(
        "/auth/admin-login",
        data={"username": "admin1", "password": "pw123"},
        follow_redirects=False,
    )
    assert login_response.status_code in (301, 302, 303)

    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code in (301, 302, 303)
    assert response.headers["Location"].endswith("/admin/stage-1")


def test_sso_auth_required_redirects_unauthenticated(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    client = app.test_client()

    response = client.get("/bookmarks")
    _assert_login_redirect(response)


def test_auth_required_preserves_forwarded_prefix_in_next(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    client = app.test_client()

    response = client.get("/bookmarks", headers={"X-Forwarded-Prefix": "/devradio"})
    assert response.status_code in (301, 302, 303, 307, 308)

    target = response.headers.get("Location", "")
    parsed = urlparse(target)
    assert parsed.path == "/auth/login"
    next_values = parse_qs(parsed.query).get("next", [])
    assert next_values and next_values[0].startswith("/devradio/bookmarks")


def test_sso_homepage_renders_without_admin_login_link(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    client = app.test_client()

    response = client.get("/")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Sign In" in page
    assert "Admin Login" not in page


def test_sso_auth_required_allows_session_user_with_profile(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    with app.app_context():
        db.session.add(
            UserProfile(
                user_id="sso-sub-1",
                username="sso-user",
                is_admin=False,
                timezone_name="Asia/Kolkata",
            )
        )
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as session_state:
        session_state["user_id"] = "sso-sub-1"
        session_state["username"] = "sso-user"
        session_state["is_admin"] = False
        session_state["timezone_name"] = "Asia/Kolkata"

    response = client.get("/bookmarks")
    assert response.status_code == 200


def test_sso_admin_required_blocks_non_admin_profile(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    with app.app_context():
        db.session.add(
            UserProfile(
                user_id="sso-sub-2",
                username="listener-sso",
                is_admin=False,
                timezone_name="Asia/Kolkata",
            )
        )
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as session_state:
        session_state["user_id"] = "sso-sub-2"
        session_state["username"] = "listener-sso"
        session_state["is_admin"] = False
        session_state["timezone_name"] = "Asia/Kolkata"

    response = client.get("/admin/")
    assert response.status_code == 403


def test_sso_admin_required_allows_admin_profile(tmp_path):
    app = _build_test_app(tmp_path, auth_mode="sso")
    with app.app_context():
        db.session.add(
            UserProfile(
                user_id="sso-sub-3",
                username="admin-sso",
                is_admin=True,
                timezone_name="Asia/Kolkata",
            )
        )
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as session_state:
        session_state["user_id"] = "sso-sub-3"
        session_state["username"] = "admin-sso"
        session_state["is_admin"] = True
        session_state["timezone_name"] = "Asia/Kolkata"

    response = client.get("/admin/", follow_redirects=False)
    assert response.status_code in (301, 302, 303)
    assert response.headers["Location"].endswith("/admin/stage-1")
