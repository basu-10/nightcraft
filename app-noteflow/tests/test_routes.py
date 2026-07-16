"""Integration tests for the NoteFlow app."""
from noteflow import create_app


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
    response = client.get("/noteflow/")
    assert response.status_code == 200


def test_app_requires_login():
    client = _client()
    response = client.get("/noteflow/app", follow_redirects=False)
    assert response.status_code == 302
    assert "/noteflow/auth/login" in response.headers["Location"]


def test_healthz_returns_ok():
    client = _client()
    response = client.get("/noteflow/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "service": "noteflow"}


def test_api_requires_auth():
    client = _client()
    response = client.get("/noteflow/api/notebook")
    assert response.status_code == 401
