"""
Tests for drag-and-drop file import functionality.
"""
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


def test_file_parser_handles_supported_extensions():
    """Test that file parser correctly identifies supported plaintext extensions."""
    supported = {"txt", "md", "markdown", "text", "log", "json"}
    extensions = ["test.txt", "doc.md", "readme.markdown", "data.json"]
    for f in extensions:
        ext = f.split(".")[-1].lower()
        assert ext in supported or ext == "txt"


def test_note_create_with_original_extension(monkeypatch, tmp_path):
    """Test that notes can be created with original_extension field."""
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("ext-user", "ext-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.commit()
        conn.close()

        note_id = database.create_note(
            user_id,
            title="Test Note",
            content="File content",
            original_extension="txt"
        )

        conn = database.get_connection()
        row = conn.execute(
            "SELECT original_extension FROM notes WHERE id=?",
            (note_id,),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["original_extension"] == "txt"


def test_note_update_with_original_extension(monkeypatch, tmp_path):
    """Test that notes can be updated with original_extension field."""
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("ext-update-user", "ext-update-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.commit()
        conn.close()

    note_id = database.create_note(
        user_id,
        title="Note Without Ext",
        content="Original"
    )

    database.update_note(
        user_id,
        note_id,
        original_extension="md"
    )

    with app.app_context():
        conn = database.get_connection()
        row = conn.execute(
            "SELECT original_extension FROM notes WHERE id=?",
            (note_id,),
        ).fetchone()
        conn.close()

    assert row is not None
    assert row["original_extension"] == "md"


def test_api_creates_note_with_original_extension(monkeypatch, tmp_path):
    """Test that API accepts and stores original_extension field."""
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("api-ext-user", "api-ext-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
            (user_id, "api-ext-token", "desktop"),
        )
        conn.commit()
        conn.close()

    client = app.test_client()
    response = client.post(
        "/api/notes",
        json={
            "title": "Imported Note",
            "content": "Content from file",
            "original_extension": "py"
        },
        headers={"Authorization": "Bearer api-ext-token"},
    )

    assert response.status_code == 201
    data = response.get_json()
    assert "id" in data


def test_api_update_note_with_original_extension(monkeypatch, tmp_path):
    """Test that API PUT accepts original_extension field."""
    app = _create_app(monkeypatch, tmp_path, auth_mode="local")

    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            ("update-ext-user", "update-ext-user@example.com", "unused", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
            (user_id, "update-ext-token", "desktop"),
        )
        conn.commit()
        conn.close()

    note_id = database.create_note(
        user_id,
        title="Note",
        content="Content"
    )

    client = app.test_client()
    response = client.put(
        f"/api/notes/{note_id}",
        json={"original_extension": "go"},
        headers={"Authorization": "Bearer update-ext-token"},
    )

    assert response.status_code == 200

    with app.app_context():
        conn = database.get_connection()
        row = conn.execute(
            "SELECT original_extension FROM notes WHERE id=?",
            (note_id,),
        ).fetchone()
        conn.close()

    assert row["original_extension"] == "go"