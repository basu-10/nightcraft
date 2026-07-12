"""
Note References — the graph-edge platform primitive for NoteStack.

A reference is the only relationship supported by NoteStack. It connects one
note to another using immutable note IDs. The storage layer calls this an
"edge" because that is what it really is: a directed edge in a note graph.
The UI layer is free to present edges as "References" and "Referenced By".

Design goals (see project brief):

  * Minimal relationship model — no relationship types, no enums, no behaviour
    flags, no path-based references. Just a directed edge with an optional
    human-readable label.
  * Relationships always use immutable note IDs, so moving / renaming / refiling
    a note never invalidates an edge.
  * Idempotent, forward-compatible, self-healing, and safe to run many times.
  * Automatic schema management — the table and its indexes are created on
    demand (and at application startup) via idempotent DDL. No manual SQL, no
    one-off setup scripts.
  * Data integrity enforced at the database layer (foreign keys with cascade
    delete, a uniqueness constraint, and a self-reference guard) and re-checked
    in the service layer so the API always returns friendly errors.
  * The rest of the application must never query the `note_edges` table
    directly — it goes through the functions in this module.

Future consumers (backlinks, graph visualization, edge labels, related notes,
traversal history, orphan detection, recommendation engine, graph analytics)
should build on top of this service rather than touching the table.
"""
from typing import Any, Optional

from . import database
from .database import get_connection, _get_last_insert_id


# ─── Schema (idempotent, self-healing) ───────────────────────────────────────
#
# The table is deliberately small and stable. New capabilities are expected to
# come from how the graph is *queried*, not from new columns. If a genuine
# schema change is ever required, add it to `_EDGE_MIGRATIONS` (lightweight
# application-managed migrations) — never ask the user to run SQL by hand.

_SQLITE_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS note_edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_note_id  INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id  INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    label           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (source_note_id <> target_note_id)
)
"""

_POSTGRES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS note_edges (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_note_id  BIGINT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    target_note_id  BIGINT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    label           TEXT NOT NULL DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (source_note_id <> target_note_id)
)
"""

# Applied on every init so missing indexes are always (re)created. This is what
# makes the schema "self-healing" across deployments: a future release can add
# an index here and every existing installation picks it up on next startup.
_EDGE_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_note_edges_user_src "
    "ON note_edges(user_id, source_note_id)",
    "CREATE INDEX IF NOT EXISTS idx_note_edges_user_tgt "
    "ON note_edges(user_id, target_note_id)",
    # Enforce (user, source, target, label) uniqueness independently of the
    # table DDL so it also applies to legacy tables created before this index
    # existed. The service layer double-checks this for friendly errors.
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_note_edges_uniq "
    "ON note_edges(user_id, source_note_id, target_note_id, label)",
]

# Forward-compatible migration hooks. Each is a callable(conn) that makes the
# schema match the current version. They run only the work that is still needed
# (guarded by information_schema / PRAGMA inspection) so they are safe to run
# repeatedly. Append new migrations here; never require manual SQL.
_EDGE_MIGRATIONS: list = []


def initialize_edge_schema() -> None:
    """Create the `note_edges` table and its indexes if they are missing.

    Idempotent and safe to call on every request. Running this on an existing
    installation leaves the schema unchanged (same end state).

    The active backend is read from ``database._DB_BACKEND`` at call time
    (never a value imported at module load) so it always reflects the runtime
    configuration set by ``configure_database()`` — this is what keeps the
    schema init correct on the PostgreSQL production deployment.
    """
    is_postgres = (database._DB_BACKEND or "sqlite").strip().lower() == "postgres"
    if is_postgres:
        conn = get_connection()
        try:
            conn.execute(_POSTGRES_TABLE_DDL)
            for stmt in _EDGE_INDEX_DDL:
                conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()
    else:
        conn = get_connection()
        try:
            if hasattr(conn, "executescript"):
                # Native sqlite3 connection.
                conn.executescript(_SQLITE_TABLE_DDL)
            else:
                # Defensive fallback: run each statement individually so a
                # non-sqlite wrapper without executescript still works.
                for statement in _split_sql_statements(_SQLITE_TABLE_DDL):
                    conn.execute(statement)
            for stmt in _EDGE_INDEX_DDL:
                conn.execute(stmt)
            conn.commit()
        finally:
            conn.close()

    for migrate in _EDGE_MIGRATIONS:
        migrate()


def _split_sql_statements(script: str) -> list:
    """Split a SQL script into individual statements on top-level semicolons."""
    statements: list = []
    current: list = []
    in_single = in_double = False
    for ch in script:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if ch == ";" and not in_single and not in_double:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(ch)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _ensure_edge_schema() -> None:
    """Lazy, self-healing guard used by every public function."""
    initialize_edge_schema()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _as_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _edge_to_dict(row: dict, partner_id: Optional[int] = None,
                  partner_title: Optional[str] = None) -> dict:
    return {
        "id": int(row["id"]),
        "user_id": int(row["user_id"]),
        "source_note_id": int(row["source_note_id"]),
        "target_note_id": int(row["target_note_id"]),
        "label": row["label"] or "",
        "created_at": row["created_at"],
        "partner_id": partner_id,
        "partner_title": partner_title,
    }


# ─── Service / repository API ─────────────────────────────────────────────────

def create_edge(user_id: int, source_note_id: Any, target_note_id: Any,
                label: str = "") -> dict:
    """Create a directed edge source_note → target_note.

    Idempotent: if an identical edge (same user, source, target, label) already
    exists it is returned instead of raising. Safe to call multiple times.

    Raises ValueError when:
      * either note id is missing / not an integer
      * a note references itself
      * either note does not exist or does not belong to the user
    """
    _ensure_edge_schema()
    user_id = int(user_id)
    source_note_id = _as_int(source_note_id)
    target_note_id = _as_int(target_note_id)
    if source_note_id is None or target_note_id is None:
        raise ValueError("source and target note ids are required")
    label = (label or "").strip()

    if source_note_id == target_note_id:
        raise ValueError("a note cannot reference itself")

    conn = get_connection()
    try:
        # Validate ownership + existence of both endpoints up front so we can
        # return a friendly error rather than a foreign-key failure.
        rows = conn.execute(
            "SELECT id FROM notes WHERE user_id=? AND id IN (?,?)",
            (user_id, source_note_id, target_note_id),
        ).fetchall()
        owned = {int(r["id"]) for r in rows}
        if source_note_id not in owned or target_note_id not in owned:
            raise ValueError("both notes must exist and belong to the user")

        existing = conn.execute(
            "SELECT * FROM note_edges "
            "WHERE user_id=? AND source_note_id=? AND target_note_id=? AND label=?",
            (user_id, source_note_id, target_note_id, label),
        ).fetchone()
        if existing is not None:
            title_row = conn.execute(
                "SELECT title FROM notes WHERE id=?", (target_note_id,)
            ).fetchone()
            return _edge_to_dict(
                existing,
                partner_id=target_note_id,
                partner_title=title_row["title"] if title_row else None,
            )

        conn.execute(
            "INSERT INTO note_edges (user_id, source_note_id, target_note_id, label) "
            "VALUES (?,?,?,?)",
            (user_id, source_note_id, target_note_id, label),
        )
        edge_id = _get_last_insert_id(conn)
        conn.commit()

        row = conn.execute("SELECT * FROM note_edges WHERE id=?", (edge_id,)).fetchone()
        title_row = conn.execute(
            "SELECT title FROM notes WHERE id=?", (target_note_id,)
        ).fetchone()
        return _edge_to_dict(
            row,
            partner_id=target_note_id,
            partner_title=title_row["title"] if title_row else None,
        )
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def delete_edge(user_id: int, edge_id: Any) -> bool:
    """Delete an edge by id, scoped to the user. Returns True if it existed."""
    _ensure_edge_schema()
    user_id = int(user_id)
    edge_id = _as_int(edge_id)
    if edge_id is None:
        return False
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM note_edges WHERE user_id=? AND id=?",
            (user_id, edge_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "DELETE FROM note_edges WHERE user_id=? AND id=?",
            (user_id, edge_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def edge_exists(user_id: int, source_note_id: Any, target_note_id: Any,
                label: Optional[str] = None) -> bool:
    """Return True if an edge (optionally with a specific label) exists."""
    _ensure_edge_schema()
    user_id = int(user_id)
    source_note_id = _as_int(source_note_id)
    target_note_id = _as_int(target_note_id)
    if source_note_id is None or target_note_id is None:
        return False
    conn = get_connection()
    try:
        sql = (
            "SELECT 1 FROM note_edges "
            "WHERE user_id=? AND source_note_id=? AND target_note_id=?"
        )
        params: list = [user_id, source_note_id, target_note_id]
        if label is not None:
            sql += " AND label=?"
            params.append(label)
        row = conn.execute(sql, params).fetchone()
        return bool(row)
    finally:
        conn.close()


def get_outgoing_edges(user_id: int, note_id: Any,
                       label: Optional[str] = None) -> list[dict]:
    """Edges where `note_id` is the source (the note's references)."""
    _ensure_edge_schema()
    user_id = int(user_id)
    note_id = _as_int(note_id)
    if note_id is None:
        return []
    conn = get_connection()
    try:
        sql = (
            "SELECT e.*, n.title AS partner_title "
            "FROM note_edges e "
            "JOIN notes n ON n.id = e.target_note_id "
            "WHERE e.user_id=? AND e.source_note_id=?"
        )
        params: list = [user_id, note_id]
        if label is not None:
            sql += " AND e.label=?"
            params.append(label)
        sql += " ORDER BY e.created_at ASC, e.id ASC"
        rows = conn.execute(sql, params).fetchall()
        return [
            _edge_to_dict(r, partner_id=int(r["target_note_id"]),
                          partner_title=r["partner_title"])
            for r in rows
        ]
    finally:
        conn.close()


def get_incoming_edges(user_id: int, note_id: Any,
                       label: Optional[str] = None) -> list[dict]:
    """Edges where `note_id` is the target (backlinks / referenced-by)."""
    _ensure_edge_schema()
    user_id = int(user_id)
    note_id = _as_int(note_id)
    if note_id is None:
        return []
    conn = get_connection()
    try:
        sql = (
            "SELECT e.*, n.title AS partner_title "
            "FROM note_edges e "
            "JOIN notes n ON n.id = e.source_note_id "
            "WHERE e.user_id=? AND e.target_note_id=?"
        )
        params: list = [user_id, note_id]
        if label is not None:
            sql += " AND e.label=?"
            params.append(label)
        sql += " ORDER BY e.created_at ASC, e.id ASC"
        rows = conn.execute(sql, params).fetchall()
        return [
            _edge_to_dict(r, partner_id=int(r["source_note_id"]),
                          partner_title=r["partner_title"])
            for r in rows
        ]
    finally:
        conn.close()


def get_edge_counts_for_notes(user_id: int, note_ids: list) -> dict:
    """Return {note_id: total_edge_count} (incoming + outgoing) for the given ids.

    Used by the note-card UI to show a compact reference indicator without
    exposing the full relationship list.
    """
    _ensure_edge_schema()
    user_id = int(user_id)
    ids = [_as_int(i) for i in (note_ids or []) if _as_int(i) is not None]
    result = {i: 0 for i in ids}
    if not ids:
        return result
    placeholders = ",".join("?" for _ in ids)
    conn = get_connection()
    try:
        rows = conn.execute(
            f"""SELECT note_id, COUNT(*) AS c FROM (
                    SELECT source_note_id AS note_id
                    FROM note_edges
                    WHERE user_id=? AND source_note_id IN ({placeholders})
                    UNION ALL
                    SELECT target_note_id AS note_id
                    FROM note_edges
                    WHERE user_id=? AND target_note_id IN ({placeholders})
                ) sub
                GROUP BY note_id""",
            [user_id, *ids, user_id, *ids],
        ).fetchall()
        for r in rows:
            result[int(r["note_id"])] = int(r["c"])
        return result
    finally:
        conn.close()


def delete_edges_for_note(user_id: int, note_id: Any) -> int:
    """Explicitly remove every edge touching `note_id`.

    Normally this is handled automatically by the database's ON DELETE CASCADE
    foreign keys when a note is deleted. This helper exists for self-healing /
    explicit cleanup (e.g. before a hard delete) and is idempotent.
    """
    _ensure_edge_schema()
    user_id = int(user_id)
    note_id = _as_int(note_id)
    if note_id is None:
        return 0
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM note_edges "
            "WHERE user_id=? AND (source_note_id=? OR target_note_id=?)",
            (user_id, note_id, note_id),
        )
        deleted = int(getattr(cur, "rowcount", 0) or 0)
        conn.commit()
        return deleted
    finally:
        conn.close()
