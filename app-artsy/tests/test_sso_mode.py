from urllib.parse import parse_qs, urlparse
import json
import os

import pytest

from curio import create_app
from curio.auth import sso_auth
from curio.extensions import db
from curio.models import CurioItem, CurioList, Review, UserProfile


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is required for PostgreSQL-backed tests.", allow_module_level=True)


def _build_sso_app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "AUTH_MODE": "sso",
            "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


class _FakeAuthService:
    def __init__(self, token_payload=None, userinfo_payload=None, token_exception=None):
        self._token_payload = token_payload or {}
        self._userinfo_payload = userinfo_payload or {}
        self._token_exception = token_exception

    def authorize_access_token(self):
        if self._token_exception is not None:
            raise self._token_exception
        return self._token_payload

    def userinfo(self, token=None):
        return self._userinfo_payload


class _FakeOAuth:
    def __init__(self, token_payload=None, userinfo_payload=None, token_exception=None):
        self.auth_service = _FakeAuthService(
            token_payload=token_payload,
            userinfo_payload=userinfo_payload,
            token_exception=token_exception,
        )


def _seed_sso_profile(user_id="sso-sub-1", username="curio-sso", is_admin=False):
    profile = UserProfile(
        user_id=user_id,
        username=username,
        display_name=username,
        is_admin=is_admin,
        is_public=True,
    )
    db.session.add(profile)
    db.session.commit()
    return profile


def _set_sso_session(client, user_id, username, is_admin=False):
    with client.session_transaction() as session_state:
        session_state["user_id"] = user_id
        session_state["username"] = username
        session_state["is_admin"] = is_admin


def test_sso_auth_required_redirects_unauthenticated(tmp_path):
    app = _build_sso_app(tmp_path)
    client = app.test_client()

    response = client.get("/me")
    assert response.status_code in (301, 302, 303, 307, 308)
    target = response.headers.get("Location", "")
    parsed = urlparse(target)
    assert parsed.path in {"/auth/login", "/curio/auth/login"}
    next_values = parse_qs(parsed.query).get("next", [])
    assert next_values and next_values[0].startswith("/me")


def test_sso_auth_required_preserves_forwarded_prefix_in_next(tmp_path):
    app = _build_sso_app(tmp_path)
    client = app.test_client()

    response = client.get("/me", headers={"X-Forwarded-Prefix": "/curio"})
    assert response.status_code in (301, 302, 303, 307, 308)

    target = response.headers.get("Location", "")
    parsed = urlparse(target)
    assert parsed.path in {"/auth/login", "/curio/auth/login"}
    next_values = parse_qs(parsed.query).get("next", [])
    assert next_values and next_values[0].startswith("/curio/me")


def test_sso_callback_creates_profile_and_session(tmp_path):
    app = _build_sso_app(tmp_path)
    original_oauth = sso_auth.oauth
    sso_auth.oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-sub-100",
            "preferred_username": "curio-user",
            "roles": ["listener"],
        },
    )

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code in (301, 302, 303)

        with app.app_context():
            profile = UserProfile.query.filter_by(user_id="sso-sub-100").first()
            assert profile is not None
            assert profile.username == "curio-user"
            assert profile.is_admin is False

        with client.session_transaction() as session_state:
            assert session_state["user_id"] == "sso-sub-100"
            assert session_state["username"] == "curio-user"
            assert session_state["is_admin"] is False
    finally:
        sso_auth.oauth = original_oauth


def test_sso_callback_rejects_invalid_state(tmp_path):
    app = _build_sso_app(tmp_path)
    if sso_auth.OAuthError is None:
        raise AssertionError("Authlib OAuthError should be available for Curio SSO tests")

    original_oauth = sso_auth.oauth
    sso_auth.oauth = _FakeOAuth(
        token_exception=sso_auth.OAuthError(error="invalid_request", description='Invalid "state" parameter')
    )

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 400
        assert 'Invalid &#34;state&#34; parameter' in response.get_data(as_text=True)
    finally:
        sso_auth.oauth = original_oauth


def test_sso_callback_redirects_to_prefixed_next_target(tmp_path):
    app = _build_sso_app(tmp_path)
    original_oauth = sso_auth.oauth
    sso_auth.oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-sub-101",
            "preferred_username": "curio-prefixed-user",
            "roles": ["listener"],
        },
    )

    try:
        client = app.test_client()
        with client.session_transaction() as session_state:
            session_state["sso_next"] = "/me"

        response = client.get("/auth/callback", headers={"X-Forwarded-Prefix": "/curio"}, follow_redirects=False)
        assert response.status_code in (301, 302, 303)
        assert response.headers.get("Location", "").startswith("/curio/me")
    finally:
        sso_auth.oauth = original_oauth


def test_sso_session_user_can_create_list_review_and_item(tmp_path):
    app = _build_sso_app(tmp_path)
    with app.app_context():
        profile = _seed_sso_profile(user_id="sso-sub-2", username="curio-sso")
        profile_id = profile.id

    client = app.test_client()
    _set_sso_session(client, user_id="sso-sub-2", username="curio-sso", is_admin=False)

    list_response = client.post(
        "/me/lists",
        data={"title": "SSO Shelf", "category": "books", "description": "SSO list"},
        follow_redirects=True,
    )
    assert list_response.status_code == 200
    assert "List created." in list_response.get_data(as_text=True)

    review_response = client.post(
        "/me/reviews",
        data={"subject": "SSO Review", "category": "books", "rating": "4", "body": "SSO body"},
        follow_redirects=True,
    )
    assert review_response.status_code == 200
    assert "Review published." in review_response.get_data(as_text=True)

    with app.app_context():
        created_list = CurioList.query.filter_by(profile_id=profile_id, title="SSO Shelf").first()
        assert created_list is not None
        assert Review.query.filter_by(profile_id=profile_id, subject="SSO Review").first() is not None
        list_id = created_list.id

    item_response = client.post(
        f"/me/lists/{list_id}/items",
        data={"title": "SSO Item", "creator_name": "Author", "notes": "note"},
        follow_redirects=True,
    )
    assert item_response.status_code == 200
    assert "List item added." in item_response.get_data(as_text=True)

    work_response = client.post(
        "/items",
        data={
            "category": "film",
            "title": "SSO Film",
            "creator_display_name": "SSO Director",
            "image_url": "https://images.example/sso-film.jpg",
            "description": "SSO-created work entry.",
            "film_director": "SSO Director",
            "film_year": "2025",
            "film_runtime_minutes": "101",
            "film_country": "India",
            "film_language": "English",
        },
        follow_redirects=True,
    )
    assert work_response.status_code == 200
    assert "Work submitted." in work_response.get_data(as_text=True)

    with app.app_context():
        created_work = CurioItem.query.filter_by(title="SSO Film").first()
        assert created_work is not None
        assert created_work.is_user_submitted is True


def test_sso_shared_auth_cookie_bootstraps_curio_session(tmp_path):
    app = _build_sso_app(tmp_path)

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {
                    "authenticated": True,
                    "user": {
                        "sub": "bridge-sub-1",
                        "preferred_username": "bridge-user",
                        "roles": ["listener"],
                        "is_admin": False,
                    },
                }
            ).encode("utf-8")

    original_urlopen = sso_auth.urllib_request.urlopen
    sso_auth.urllib_request.urlopen = lambda *args, **kwargs: _FakeResponse()

    try:
        client = app.test_client()
        response = client.get("/")
        assert response.status_code == 200

        with client.session_transaction() as session_state:
            assert session_state["user_id"] == "bridge-sub-1"
            assert session_state["username"] == "bridge-user"
            assert session_state["is_admin"] is False

        with app.app_context():
            profile = UserProfile.query.filter_by(user_id="bridge-sub-1").first()
            assert profile is not None
            assert profile.username == "bridge-user"
    finally:
        sso_auth.urllib_request.urlopen = original_urlopen


def test_curio_admin_page_forbidden_for_non_admin_sso_user(tmp_path):
    app = _build_sso_app(tmp_path)
    with app.app_context():
        _seed_sso_profile(user_id="sso-sub-non-admin", username="plain-user", is_admin=False)

    client = app.test_client()
    _set_sso_session(client, user_id="sso-sub-non-admin", username="plain-user", is_admin=False)

    response = client.get("/admin")
    assert response.status_code == 403


def test_curio_admin_page_renders_for_admin_sso_user(tmp_path):
    app = _build_sso_app(tmp_path)
    with app.app_context():
        _seed_sso_profile(user_id="sso-sub-admin", username="admin-user", is_admin=True)

    client = app.test_client()
    _set_sso_session(client, user_id="sso-sub-admin", username="admin-user", is_admin=True)

    response = client.get("/admin")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Curio Admin" in page
    assert "Platform Stats" in page
