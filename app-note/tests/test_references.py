import importlib
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _create_app(monkeypatch, tmp_path):
    db_path = tmp_path / "notestack.db"
    monkeypatch.setenv("NOTESTACK_DB", str(db_path))
    monkeypatch.setenv("NOTESTACK_DB_BACKEND", "sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_MODE", "local")
    monkeypatch.setenv("FLASK_ENV", "development")

    import app as note_app

    importlib.reload(note_app)
    flask_app = note_app.create_app()
    flask_app.config.update(TESTING=True)
    return flask_app


def _seed_user_with_notes(app, username):
    import app.database as database

    with app.app_context():
        conn = database.get_connection()
        conn.execute(
            "INSERT INTO users (username, email, password, is_admin) VALUES (?,?,?,?)",
            (username, f"{username}@example.com", "x", 0),
        )
        user_id = int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])
        conn.execute(
            "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
            (user_id, f"tok-{username}", "desktop"),
        )
        note_ids = []
        for title in ("Note A", "Note B", "Note C"):
            conn.execute(
                "INSERT INTO notes (user_id, title, content, sync_id, server_rev) VALUES (?,?,?,?,?)",
                (user_id, title, "body", f"sync-{username}-{title}", 1),
            )
            note_ids.append(int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]))
        conn.commit()
        conn.close()
    return user_id, note_ids


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ─── Repository (service) ────────────────────────────────────────────────────

def test_create_and_query_edges(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    user_id, (a, b, c) = _seed_user_with_notes(app, "edge-user-1")

    import app.references as refs

    with app.app_context():
        e1 = refs.create_edge(user_id, a, b, "uses")
        assert e1["source_note_id"] == a and e1["target_note_id"] == b
        assert e1["label"] == "uses"
        assert e1["partner_id"] == b

        # idempotent: same edge returns the existing one, no error
        e1b = refs.create_edge(user_id, a, b, "uses")
        assert e1b["id"] == e1["id"]

        refs.create_edge(user_id, a, c, "")
        refs.create_edge(user_id, b, a, "")

        outgoing = refs.get_outgoing_edges(user_id, a)
        assert {e["partner_id"] for e in outgoing} == {b, c}

        incoming = refs.get_incoming_edges(user_id, a)
        assert {e["partner_id"] for e in incoming} == {b}

        assert refs.edge_exists(user_id, a, b, "uses") is True
        assert refs.edge_exists(user_id, a, b, "other") is False

        counts = refs.get_edge_counts_for_notes(user_id, [a, b, c])
        assert counts[a] == 3  # out: b,c ; in: b
        assert counts[b] == 2  # out: a ; in: a
        assert counts[c] == 1  # in: a


def test_self_reference_rejected(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    user_id, (a, b, c) = _seed_user_with_notes(app, "edge-user-2")

    import app.references as refs

    with app.app_context():
        with pytest.raises(ValueError):
            refs.create_edge(user_id, a, a)
        # cross-user note must not be linkable
        with pytest.raises(ValueError):
            refs.create_edge(user_id, a, 999999)


def test_delete_edge_and_cascade_on_note_delete(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    user_id, (a, b, c) = _seed_user_with_notes(app, "edge-user-3")

    import app.references as refs
    import app.database as database

    with app.app_context():
        refs.create_edge(user_id, a, b, "")
        refs.create_edge(user_id, c, a, "")

        assert refs.delete_edge(user_id, 123456) is False
        edge = refs.create_edge(user_id, a, c, "")
        assert refs.delete_edge(user_id, edge["id"]) is True

        # Deleting a note cascades: all edges touching it are removed.
        database.delete_note(user_id, a)
        assert refs.get_outgoing_edges(user_id, a) == []
        assert refs.get_incoming_edges(user_id, a) == []
        # the edge from c -> a is gone too
        assert refs.get_outgoing_edges(user_id, c) == []


# ─── API ─────────────────────────────────────────────────────────────────────

def test_api_reference_lifecycle(monkeypatch, tmp_path):
    app = _create_app(monkeypatch, tmp_path)
    user_id, (a, b, c) = _seed_user_with_notes(app, "edge-api-1")
    client = app.test_client()

    # create outgoing reference
    r = client.post(
        f"/api/notes/{a}/edges",
        headers=_auth("tok-edge-api-1"),
        json={"target_note_id": b, "label": "uses decorators internally"},
    )
    assert r.status_code == 200
    edge_id = r.get_json()["edge"]["id"]

    # outgoing list
    out = client.get(f"/api/notes/{a}/edges/outgoing", headers=_auth("tok-edge-api-1"))
    assert out.status_code == 200
    assert out.get_json()["total"] == 1
    assert out.get_json()["edges"][0]["partner_title"] == "Note B"

    # incoming list on target
    inc = client.get(f"/api/notes/{b}/edges/incoming", headers=_auth("tok-edge-api-1"))
    assert inc.get_json()["total"] == 1
    assert inc.get_json()["edges"][0]["partner_title"] == "Note A"

    # counts endpoint
    counts = client.get(
        f"/api/edges/counts?ids={a},{b},{c}", headers=_auth("tok-edge-api-1")
    )
    assert counts.get_json()["counts"][str(a)] == 1

    # self-reference rejected with 400
    bad = client.post(
        f"/api/notes/{a}/edges",
        headers=_auth("tok-edge-api-1"),
        json={"target_note_id": a},
    )
    assert bad.status_code == 400

    # delete
    d = client.delete(f"/api/notes/{a}/edges/{edge_id}", headers=_auth("tok-edge-api-1"))
    assert d.status_code == 200
    assert client.get(f"/api/notes/{a}/edges/outgoing", headers=_auth("tok-edge-api-1")).get_json()["total"] == 0
