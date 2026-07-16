"""Integration tests for the ScratchPad app."""
from scratchpad import create_app


def _client():
    app = create_app(
        test_config={
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "AUTH_MODE": "local",
        }
    )
    return app.test_client()


def test_landing_renders():
    client = _client()
    response = client.get("/scratchpad/")
    assert response.status_code == 200


def test_app_requires_login():
    client = _client()
    response = client.get("/scratchpad/app", follow_redirects=False)
    assert response.status_code == 302
    assert "/scratchpad/auth/login" in response.headers["Location"]


def test_healthz_returns_ok():
    client = _client()
    response = client.get("/scratchpad/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "scratchpad"}


def test_api_requires_auth():
    client = _client()
    response = client.get("/scratchpad/api/pad")
    assert response.status_code == 401
