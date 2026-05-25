import importlib
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _create_app(monkeypatch, tmp_path, *, auth_mode="local", auth_service_url="http://auth.example/auth"):
    db_path = tmp_path / "notestack.db"
    monkeypatch.setenv("NOTESTACK_DB", str(db_path))
    monkeypatch.setenv("NOTESTACK_DB_BACKEND", "sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_MODE", auth_mode)
    monkeypatch.setenv("AUTH_SERVICE_URL", auth_service_url)
    monkeypatch.setenv("FLASK_ENV", "development")

    import app as note_app

    importlib.reload(note_app)
    flask_app = note_app.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


def test_prefixed_sso_login_redirects_to_shared_auth(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="sso")
    client = app.test_client()

    response = client.get("/auth/login?next=/app", headers={"X-Forwarded-Prefix": "/notestack"})

    assert response.status_code == 302
    assert response.headers["Location"] == "http://auth.example/auth/login?next=%2Fnotestack%2Fapp"


def test_shared_session_claims_provision_local_user(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="sso")

    import app.auth.sso_auth as sso_auth
    import app.database as database

    monkeypatch.setattr(
        sso_auth,
        "_claims_from_shared_session",
        lambda: {
            "sub": "auth-user-1",
            "preferred_username": "stack-user",
            "email": "stack-user@example.com",
            "roles": ["member", "admin"],
        },
    )

    client = app.test_client()
    response = client.get("/app")

    assert response.status_code == 200

    with app.app_context():
        conn = database.get_connection()
        row = conn.execute(
            "SELECT username, email, is_admin, sso_subject FROM users WHERE sso_subject=?",
            ("auth-user-1",),
        ).fetchone()
        conn.close()

    assert row is not None
    assert row["username"] == "stack-user"
    assert row["email"] == "stack-user@example.com"
    assert int(row["is_admin"]) == 1


def test_api_accepts_bearer_token(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("token-user", "token-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
            (user_id, "desktop-token", "desktop"),
        )
        conn.commit()
        conn.close()

    client = app.test_client()
    response = client.get(
        "/api/folders",
        headers={"Authorization": "Bearer desktop-token"},
    )

    assert response.status_code == 200
    assert response.get_json() == []