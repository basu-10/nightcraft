import importlib
import os
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _postgres_test_url() -> str | None:
    return (os.environ.get("NOTESTACK_TEST_DATABASE_URL") or "").strip() or None


def _create_postgres_app(monkeypatch):
    db_url = _postgres_test_url()
    if not db_url:
        pytest.skip("Set NOTESTACK_TEST_DATABASE_URL to run PostgreSQL integration tests")

    monkeypatch.setenv("NOTESTACK_DB_BACKEND", "postgres")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("FLASK_ENV", "development")

    import app as note_app

    importlib.reload(note_app)
    flask_app = note_app.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


def _reset_postgres_state(database):
    conn = database.get_connection()
    conn.execute(
        """
        TRUNCATE TABLE
            note_tags,
            conflicts,
            note_tombstones,
            tag_tombstones,
            folder_tombstones,
            sync_idempotency,
            note_edges,
            notes,
            tags,
            folders,
            api_tokens,
            trash,
            users,
            sync_meta
        RESTART IDENTITY CASCADE
        """
    )
    conn.execute("INSERT INTO sync_meta (id, next_server_rev) VALUES (1, 1)")
    conn.commit()
    conn.close()


def _seed_user_token(database, username: str = "pg-user", token: str = "pg-token") -> int:
    conn = database.get_connection()
    conn.execute(
        "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
        (username, f"{username}@example.com", "unused", 0),
    )
    user_id = database._get_last_insert_id(conn)
    conn.execute(
        "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
        (user_id, token, "desktop"),
    )
    conn.commit()
    conn.close()
    return int(user_id)


@pytest.mark.integration
def test_postgres_sync_push_pull_roundtrip(monkeypatch):
    app = _create_postgres_app(monkeypatch)

    import app.database as database

    with app.app_context():
        _reset_postgres_state(database)
        _seed_user_token(database, token="pg-sync-token")

    client = app.test_client()
    push_response = client.post(
        "/api/sync/push",
        headers={"Authorization": "Bearer pg-sync-token"},
        json={
            "notes": [
                {
                    "sync_id": "note-sync-1",
                    "title": "Postgres Note",
                    "content": "hello from postgres",
                    "updated_at": "2026-05-25T10:00:00Z",
                    "server_rev": 0,
                    "is_favorite": True,
                    "tags": "alpha,beta",
                }
            ]
        },
    )

    assert push_response.status_code == 200
    push_payload = push_response.get_json()
    assert push_payload["results"][0]["status"] == "created"
    assert int(push_payload["results"][0]["server_rev"]) >= 1

    pull_response = client.get(
        "/api/sync/pull?since_rev=0",
        headers={"Authorization": "Bearer pg-sync-token"},
    )

    assert pull_response.status_code == 200
    pull_payload = pull_response.get_json()
    assert len(pull_payload["notes"]) == 1
    note = pull_payload["notes"][0]
    assert note["sync_id"] == "note-sync-1"
    assert note["title"] == "Postgres Note"
    assert set((note.get("tags") or "").split(",")) == {"alpha", "beta"}
    assert int(pull_payload["since_rev"]) >= int(push_payload["results"][0]["server_rev"])


@pytest.mark.integration
def test_postgres_sync_idempotency_replay(monkeypatch):
    app = _create_postgres_app(monkeypatch)

    import app.database as database

    with app.app_context():
        _reset_postgres_state(database)
        _seed_user_token(database, token="pg-idem-token")

    client = app.test_client()
    headers = {
        "Authorization": "Bearer pg-idem-token",
        "X-Idempotency-Key": "idem-folder-1",
        "X-Correlation-ID": "corr-1",
    }
    body = {
        "folders": [
            {"sync_id": "folder-sync-1", "name": "Inbox", "color": "#ABCDEF"}
        ]
    }

    first = client.post("/api/sync/push-folders", headers=headers, json=body)
    second = client.post("/api/sync/push-folders", headers=headers, json=body)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json() == second.get_json()

    with app.app_context():
        conn = database.get_connection()
        folder_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM folders WHERE sync_id=?",
                ("folder-sync-1",),
            ).fetchone()["c"]
        )
        idem_count = int(
            conn.execute(
                "SELECT COUNT(*) AS c FROM sync_idempotency WHERE idem_key=?",
                ("idem-folder-1",),
            ).fetchone()["c"]
        )
        conn.close()

    assert folder_count == 1
    assert idem_count == 1
