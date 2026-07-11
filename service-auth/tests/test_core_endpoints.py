import os

import pytest

from serviceauth import create_app
from serviceauth.extensions import db
from serviceauth.models import AuthorizationCode, OauthClient, User
import jwt


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is required for PostgreSQL-backed tests.", allow_module_level=True)


def _make_test_app(extra_config=None):
    config = {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": TEST_DATABASE_URL,
        "SECRET_KEY": "test-secret",
    }
    if extra_config:
        config.update(extra_config)
    return create_app(config)


def test_healthz():
    app = _make_test_app()
    client = app.test_client()

    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"


def test_openid_configuration_contains_required_fields():
    app = _make_test_app(
        {
            "OIDC_ISSUER": "http://localhost:5100",
        }
    )
    client = app.test_client()

    response = client.get("/.well-known/openid-configuration")
    assert response.status_code == 200
    body = response.get_json()

    assert body["issuer"] == "http://localhost:5100"
    assert body["authorization_endpoint"] == "http://localhost:5100/oauth/authorize"
    assert body["token_endpoint"] == "http://localhost:5100/oauth/token"
    assert body["jwks_uri"] == "http://localhost:5100/oauth/jwks"
    assert body["userinfo_endpoint"] == "http://localhost:5100/userinfo"
    assert "roles" in body["claims_supported"]
    assert "is_admin" in body["claims_supported"]


def test_jwks_endpoint_returns_key_set():
    app = _make_test_app()
    client = app.test_client()

    response = client.get("/oauth/jwks")
    assert response.status_code == 200
    body = response.get_json()
    assert "keys" in body
    assert isinstance(body["keys"], list)
    with app.app_context():
        expected_kid = app.extensions["signing_keys"]["kid"]
    assert body["keys"][0]["kid"] == expected_kid
    assert body["keys"][0]["alg"] == "RS256"


def test_register_then_login_redirects_to_next():
    app = _make_test_app()
    client = app.test_client()

    register_response = client.post(
        "/register",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "secret123",
        },
        follow_redirects=False,
    )
    assert register_response.status_code == 302
    assert register_response.headers["Location"].endswith("/login")

    login_response = client.post(
        "/login?next=/healthz",
        data={"username": "alice", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302
    assert login_response.headers["Location"].endswith("/healthz")


def test_login_redirect_preserves_forwarded_prefix_for_oauth_next():
    app = _make_test_app()
    client = app.test_client()

    client.post(
        "/register",
        data={
            "username": "prefixed-user",
            "email": "prefixed-user@example.com",
            "password": "secret123",
        },
        follow_redirects=False,
    )

    response = client.post(
        "/login?next=/oauth/authorize?client_id=radio-app",
        data={"username": "prefixed-user", "password": "secret123"},
        headers={"X-Forwarded-Prefix": "/auth"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"] == "/auth/oauth/authorize?client_id=radio-app"


def test_login_rejects_external_next_redirect():
    app = _make_test_app()
    client = app.test_client()

    client.post(
        "/register",
        data={
            "username": "safe-user",
            "email": "safe-user@example.com",
            "password": "secret123",
        },
        follow_redirects=False,
    )

    response = client.post(
        "/login?next=https://example.com/evil",
        data={"username": "safe-user", "password": "secret123"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/healthz")


def test_register_allows_sparse_form_data():
    app = _make_test_app()
    client = app.test_client()

    response = client.post(
        "/register",
        data={
            "password": "secret123",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with app.app_context():
        user = User.query.one()
        assert user.username.startswith("user-")
        assert user.email.endswith("@local.invalid")
        assert user.timezone_name == "Asia/Kolkata"


def test_login_page_includes_google_sign_in_link():
    app = _make_test_app()
    client = app.test_client()

    response = client.get("/login")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert "Continue with Google" in page
    assert "Login" in page


def test_login_page_static_url_honors_forwarded_prefix():
    app = _make_test_app()
    client = app.test_client()

    response = client.get("/login", headers={"X-Forwarded-Prefix": "/auth"})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'href="/auth/static/css/main.css"' in page


def test_authorize_redirects_to_login_when_unauthenticated():
    app = _make_test_app()
    with app.app_context():
        db.session.add(
            OauthClient(
                client_id="radio-app",
                client_secret="dev-secret",
                redirect_uris="http://localhost:5000/auth/callback",
            )
        )
        db.session.commit()

    client = app.test_client()
    response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=abc123",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].startswith("/login?next=")


def test_authorize_issues_code_after_login():
    app = _make_test_app()
    with app.app_context():
        user = User(username="bob", email="bob@example.com", password_hash="")
        user.set_password("secret123")
        db.session.add(user)
        db.session.add(
            OauthClient(
                client_id="radio-app",
                client_secret="dev-secret",
                redirect_uris="http://localhost:5000/auth/callback",
            )
        )
        db.session.commit()

    client = app.test_client()
    login_response = client.post(
        "/login",
        data={"username": "bob", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    authorize_response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=xyz",
        follow_redirects=False,
    )

    assert authorize_response.status_code == 302
    location = authorize_response.headers["Location"]
    assert location.startswith("http://localhost:5000/auth/callback?code=")
    assert "&state=xyz" in location

    with app.app_context():
        stored = AuthorizationCode.query.count()
        assert stored == 1


def test_authorize_rejects_redirect_uri_mismatch():
    app = _make_test_app()
    with app.app_context():
        user = User(username="carol", email="carol@example.com", password_hash="")
        user.set_password("secret123")
        db.session.add(user)
        db.session.add(
            OauthClient(
                client_id="radio-app",
                client_secret="dev-secret",
                redirect_uris="http://localhost:5000/auth/callback",
            )
        )
        db.session.commit()

    client = app.test_client()
    client.post(
        "/login",
        data={"username": "carol", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/evil-callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=xyz",
        follow_redirects=False,
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "invalid_request"


def _seed_user_and_client(app, username="token-user", email="token@example.com", is_admin=False):
    with app.app_context():
        user = User(username=username, email=email, password_hash="", is_admin=is_admin)
        user.set_password("secret123")
        db.session.add(user)
        db.session.add(
            OauthClient(
                client_id="radio-app",
                client_secret="dev-secret",
                redirect_uris="http://localhost:5000/auth/callback",
            )
        )
        db.session.commit()


def _login_and_get_code(client):
    login_response = client.post(
        "/login",
        data={"username": "token-user", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    authorize_response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=token-state",
        follow_redirects=False,
    )
    assert authorize_response.status_code == 302
    location = authorize_response.headers["Location"]
    code = location.split("code=", 1)[1].split("&", 1)[0]
    return code


def _login_and_get_code_with_nonce(client, nonce):
    login_response = client.post(
        "/login",
        data={"username": "token-user", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    authorize_response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        f"&nonce={nonce}"
        "&state=token-state",
        follow_redirects=False,
    )
    assert authorize_response.status_code == 302
    location = authorize_response.headers["Location"]
    code = location.split("code=", 1)[1].split("&", 1)[0]
    return code


def test_token_exchange_and_userinfo_success():
    app = _make_test_app({"OIDC_ISSUER": "http://localhost:5100"})
    _seed_user_and_client(app)
    client = app.test_client()

    code = _login_and_get_code(client)
    token_response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "dev-secret",
        },
    )
    assert token_response.status_code == 200
    token_body = token_response.get_json()
    assert token_body["token_type"] == "Bearer"
    assert "access_token" in token_body
    assert "id_token" in token_body

    userinfo_response = client.get(
        "/userinfo",
        headers={"Authorization": f"Bearer {token_body['access_token']}"},
    )
    assert userinfo_response.status_code == 200
    claims = userinfo_response.get_json()
    assert claims["preferred_username"] == "token-user"
    assert claims["email"] == "token@example.com"
    assert claims["roles"] == ["listener"]
    assert claims["is_admin"] is False


def test_token_exchange_includes_id_token_nonce_when_requested():
    app = _make_test_app({"OIDC_ISSUER": "http://localhost:5100"})
    _seed_user_and_client(app)
    client = app.test_client()

    code = _login_and_get_code_with_nonce(client, "nonce-123")
    token_response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "dev-secret",
        },
    )
    assert token_response.status_code == 200
    token_body = token_response.get_json()

    decoded = jwt.decode(
        token_body["id_token"],
        app.extensions["signing_keys"]["public_key"],
        algorithms=["RS256"],
        audience="radio-app",
        options={"verify_iss": False, "verify_signature": True},
    )
    assert decoded["nonce"] == "nonce-123"
    assert decoded["preferred_username"] == "token-user"
    assert decoded["roles"] == ["listener"]
    assert decoded["is_admin"] is False


def test_token_exchange_emits_admin_role_and_derived_admin_claim():
    app = _make_test_app({"OIDC_ISSUER": "http://localhost:5100"})
    _seed_user_and_client(app, username="admin-user", email="admin@example.com", is_admin=True)
    client = app.test_client()

    login_response = client.post(
        "/login",
        data={"username": "admin-user", "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302

    authorize_response = client.get(
        "/oauth/authorize"
        "?client_id=radio-app"
        "&redirect_uri=http://localhost:5000/auth/callback"
        "&response_type=code"
        "&scope=openid%20profile%20email"
        "&state=admin-state",
        follow_redirects=False,
    )
    assert authorize_response.status_code == 302
    location = authorize_response.headers["Location"]
    code = location.split("code=", 1)[1].split("&", 1)[0]

    token_response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "dev-secret",
        },
    )
    assert token_response.status_code == 200
    token_body = token_response.get_json()

    userinfo_response = client.get(
        "/userinfo",
        headers={"Authorization": f"Bearer {token_body['access_token']}"},
    )
    assert userinfo_response.status_code == 200
    claims = userinfo_response.get_json()
    assert claims["roles"] == ["admin"]
    assert claims["is_admin"] is True

    decoded = jwt.decode(
        token_body["id_token"],
        app.extensions["signing_keys"]["public_key"],
        algorithms=["RS256"],
        audience="radio-app",
        options={"verify_iss": False, "verify_signature": True},
    )
    assert decoded["roles"] == ["admin"]
    assert decoded["is_admin"] is True


def test_token_exchange_rejects_reused_code():
    app = _make_test_app()
    _seed_user_and_client(app)
    client = app.test_client()

    code = _login_and_get_code(client)
    first = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "dev-secret",
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "dev-secret",
        },
    )
    assert second.status_code == 400
    second_body = second.get_json()
    assert second_body["error"] == "invalid_grant"


def test_token_exchange_rejects_invalid_client_credentials():
    app = _make_test_app()
    _seed_user_and_client(app)
    client = app.test_client()
    code = _login_and_get_code(client)

    response = client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "http://localhost:5000/auth/callback",
            "client_id": "radio-app",
            "client_secret": "wrong-secret",
        },
    )
    assert response.status_code == 401
    body = response.get_json()
    assert body["error"] == "invalid_client"


def test_userinfo_rejects_missing_or_invalid_token():
    app = _make_test_app()
    client = app.test_client()

    missing = client.get("/userinfo")
    assert missing.status_code == 401
    missing_body = missing.get_json()
    assert missing_body["error"] == "invalid_token"

    invalid = client.get("/userinfo", headers={"Authorization": "Bearer not-a-real-token"})
    assert invalid.status_code == 401
    invalid_body = invalid.get_json()
    assert invalid_body["error"] == "invalid_token"


def test_session_me_reports_unauthenticated_without_session():
    app = _make_test_app()
    client = app.test_client()

    response = client.get("/session/me")
    assert response.status_code == 200
    assert response.get_json() == {"authenticated": False}


def test_session_me_returns_claims_for_authenticated_session():
    app = _make_test_app()
    client = app.test_client()

    client.post(
        "/register",
        data={
            "username": "session-user",
            "email": "session-user@example.com",
            "password": "secret123",
        },
        follow_redirects=False,
    )

    response = client.get("/session/me")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["authenticated"] is True
    assert payload["user"]["preferred_username"] == "session-user"
    assert payload["user"]["email"] == "session-user@example.com"
    assert payload["user"]["roles"] == ["listener"]
    assert payload["user"]["is_admin"] is False


def _seed_admin_and_login(app, client, username="admin-user", email="admin@example.com"):
    with app.app_context():
        admin = User(username=username, email=email, password_hash="", is_admin=True)
        admin.set_password("secret123")
        db.session.add(admin)
        db.session.commit()

    login_response = client.post(
        "/login",
        data={"username": username, "password": "secret123"},
        follow_redirects=False,
    )
    assert login_response.status_code == 302


def test_admin_users_requires_admin_role():
    app = _make_test_app()
    client = app.test_client()

    client.post(
        "/register",
        data={"username": "plain-user", "email": "plain@example.com", "password": "secret123"},
        follow_redirects=False,
    )

    response = client.get("/admin/users")
    assert response.status_code == 401

    client.post(
        "/login",
        data={"username": "plain-user", "password": "secret123"},
        follow_redirects=False,
    )
    authed = client.get("/admin/users")
    assert authed.status_code == 403


def test_admin_users_lists_users_for_admin():
    app = _make_test_app()
    client = app.test_client()
    _seed_admin_and_login(app, client)

    response = client.get("/admin/users")
    assert response.status_code == 200
    body = response.get_json()
    assert body["total"] >= 1
    assert any(u["username"] == "admin-user" for u in body["users"])


def test_admin_logs_returns_activity_and_stats():
    app = _make_test_app()
    client = app.test_client()
    _seed_admin_and_login(app, client)

    response = client.get("/admin/logs")
    assert response.status_code == 200
    body = response.get_json()
    assert "activity" in body
    assert "clients" in body
    assert "stats" in body
    assert body["stats"]["users"] >= 1


def test_admin_delete_user_forbids_self_delete():
    app = _make_test_app()
    client = app.test_client()
    _seed_admin_and_login(app, client)

    with app.app_context():
        admin_id = User.query.filter_by(username="admin-user").first().id

    response = client.delete(f"/admin/users/{admin_id}")
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"] == "self_delete"
