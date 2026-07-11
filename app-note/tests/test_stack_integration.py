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


def test_guest_mode_app_access_without_session(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="sso")

    import app.auth.sso_auth as sso_auth

    monkeypatch.setattr(sso_auth, "_claims_from_shared_session", lambda: None)

    client = app.test_client()
    response = client.get("/app")

    assert response.status_code == 200
    assert b"window.NOTESTACK_IS_GUEST = true" in response.data


def test_guest_mode_settings_still_requires_login(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="sso")

    import app.auth.sso_auth as sso_auth

    monkeypatch.setattr(sso_auth, "_claims_from_shared_session", lambda: None)

    client = app.test_client()
    response = client.get("/settings")

    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


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


def test_delete_all_data_removes_user_content(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("wipe-user", "wipe-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
            (user_id, "wipe-token", "desktop"),
        )
        conn.execute(
            "INSERT INTO folders (user_id, name, sync_id) VALUES (?,?,?)",
            (user_id, "Folder 1", "sync-folder-1"),
        )
        conn.execute(
            "INSERT INTO tags (user_id, name, sync_id) VALUES (?,?,?)",
            (user_id, "Tag 1", "sync-tag-1"),
        )
        conn.execute(
            "INSERT INTO notes (user_id, title, content, sync_id, server_rev) VALUES (?,?,?,?,?)",
            (user_id, "Note 1", "body", "sync-note-1", 1),
        )
        conn.execute(
            "INSERT INTO trash (user_id, title, content, created_at, updated_at) VALUES (?,?,?,?,?)",
            (user_id, "Trashed", "x", "2024-01-01T00:00:00", "2024-01-01T00:00:00"),
        )
        conn.commit()
        conn.close()

    client = app.test_client()
    response = client.post(
        "/api/data/delete-all",
        headers={"Authorization": "Bearer wipe-token"},
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["deleted"] is True

    with app.app_context():
        conn = database.get_connection()
        folders = int(conn.execute("SELECT COUNT(*) AS c FROM folders WHERE user_id=?", (user_id,)).fetchone()["c"])
        notes = int(conn.execute("SELECT COUNT(*) AS c FROM notes WHERE user_id=?", (user_id,)).fetchone()["c"])
        tags = int(conn.execute("SELECT COUNT(*) AS c FROM tags WHERE user_id=?", (user_id,)).fetchone()["c"])
        trash = int(conn.execute("SELECT COUNT(*) AS c FROM trash WHERE user_id=?", (user_id,)).fetchone()["c"])
        tokens = int(conn.execute("SELECT COUNT(*) AS c FROM api_tokens WHERE user_id=?", (user_id,)).fetchone()["c"])
        conn.close()

    assert folders == 0
    assert notes == 0
    assert tags == 0
    assert trash == 0
    # Account and API tokens are preserved.
    assert tokens == 1
