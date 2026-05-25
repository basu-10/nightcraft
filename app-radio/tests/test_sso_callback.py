import os

import pytest

from devradio import create_app
from devradio.extensions import db
from devradio.models import UserProfile
from devradio.auth import sso_auth


class _FakeAuthService:
    def __init__(self, token_payload, userinfo_payload, token_exception=None):
        self._token_payload = token_payload
        self._userinfo_payload = userinfo_payload
        self._token_exception = token_exception

    def authorize_access_token(self):
        if self._token_exception is not None:
            raise self._token_exception
        return self._token_payload

    def userinfo(self, token=None):
        return self._userinfo_payload


class _FakeOAuth:
    def __init__(self, token_payload, userinfo_payload, token_exception=None):
        self.auth_service = _FakeAuthService(token_payload, userinfo_payload, token_exception=token_exception)


def _build_sso_app(tmp_path):
    database_uri = os.getenv("TEST_DATABASE_URL")
    if not database_uri:
        pytest.skip("Set TEST_DATABASE_URL to run app-radio tests against PostgreSQL.")

    app = create_app(
        {
            "TESTING": True,
            "AUTH_MODE": "sso",
            "SQLALCHEMY_DATABASE_URI": database_uri,
        }
    )
    with app.app_context():
        db.drop_all()
        db.create_all()
    return app


def test_sso_callback_fetches_userinfo_when_missing_in_token(tmp_path):
    app = _build_sso_app(tmp_path)
    fake_oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-001",
            "preferred_username": "radio-sso-user",
            "roles": ["listener"],
            "timezone_name": "Asia/Kolkata",
        },
    )
    original = sso_auth.oauth
    sso_auth.oauth = fake_oauth

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code in (301, 302, 303)

        with app.app_context():
            profile = UserProfile.query.filter_by(user_id="sso-001").first()
            assert profile is not None
            assert profile.username == "radio-sso-user"
            assert profile.is_admin is False
            assert profile.timezone_name == "Asia/Kolkata"

        with client.session_transaction() as session_state:
            assert session_state["user_id"] == "sso-001"
            assert session_state["username"] == "radio-sso-user"
            assert session_state["is_admin"] is False
    finally:
        sso_auth.oauth = original


def test_sso_callback_maps_admin_from_roles_claim(tmp_path):
    app = _build_sso_app(tmp_path)
    fake_oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-002",
            "preferred_username": "admin-user",
            "roles": ["listener", "admin"],
            "timezone_name": "Asia/Kolkata",
        },
    )
    original = sso_auth.oauth
    sso_auth.oauth = fake_oauth

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code in (301, 302, 303)

        with app.app_context():
            profile = UserProfile.query.filter_by(user_id="sso-002").first()
            assert profile is not None
            assert profile.is_admin is True
    finally:
        sso_auth.oauth = original


def test_sso_callback_uses_derived_is_admin_when_roles_missing(tmp_path):
    app = _build_sso_app(tmp_path)
    fake_oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-003",
            "preferred_username": "derived-admin",
            "is_admin": True,
            "timezone_name": "Asia/Kolkata",
        },
    )
    original = sso_auth.oauth
    sso_auth.oauth = fake_oauth

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code in (301, 302, 303)

        with app.app_context():
            profile = UserProfile.query.filter_by(user_id="sso-003").first()
            assert profile is not None
            assert profile.is_admin is True
    finally:
        sso_auth.oauth = original


def test_sso_callback_rejects_invalid_state(tmp_path):
    app = _build_sso_app(tmp_path)
    if sso_auth.OAuthError is None:
        raise AssertionError("Authlib OAuthError should be available for SSO tests")

    fake_oauth = _FakeOAuth(
        token_payload=None,
        userinfo_payload=None,
        token_exception=sso_auth.OAuthError(error="invalid_request", description='Invalid "state" parameter'),
    )
    original = sso_auth.oauth
    sso_auth.oauth = fake_oauth

    try:
        client = app.test_client()
        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 400
        assert 'Invalid &#34;state&#34; parameter' in response.get_data(as_text=True)
    finally:
        sso_auth.oauth = original


def test_sso_callback_redirects_to_prefixed_next_target(tmp_path):
    app = _build_sso_app(tmp_path)
    fake_oauth = _FakeOAuth(
        token_payload={"access_token": "abc", "token_type": "Bearer"},
        userinfo_payload={
            "sub": "sso-004",
            "preferred_username": "radio-sso-prefixed",
            "roles": ["listener"],
            "timezone_name": "Asia/Kolkata",
        },
    )
    original = sso_auth.oauth
    sso_auth.oauth = fake_oauth

    try:
        client = app.test_client()
        with client.session_transaction() as session_state:
            session_state["sso_next"] = "/bookmarks"

        response = client.get("/auth/callback", headers={"X-Forwarded-Prefix": "/devradio"}, follow_redirects=False)
        assert response.status_code in (301, 302, 303)
        assert response.headers.get("Location", "").startswith("/devradio/bookmarks")
    finally:
        sso_auth.oauth = original
