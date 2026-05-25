"""
Database layer for NoteStack Web.

Schema mirrors the desktop app with user_id added for multi-user support.
sync_id (UUID) is assigned by the desktop to track the same note across devices.
"""
import colorsys
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from werkzeug.security import generate_password_hash

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - optional at runtime unless postgres backend is enabled
    psycopg = None
    dict_row = None

# Overwritten by the app factory with the config-resolved path
_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notestack.db")
_DB_BACKEND: str = "sqlite"
_DATABASE_URL: str = ""

DEFAULT_ENTITY_COLORS = [
    "#4F6EF7",
    "#22C55E",
    "#F59E0B",
    "#EC4899",
    "#06B6D4",
    "#A855F7",
    "#EF4444",
    "#84CC16",
    "#F97316",
    "#14B8A6",
    "#8B5CF6",
    "#3B82F6",
    "#10B981",
    "#EAB308",
    "#D946EF",
]


def configure_database(cfg: Any) -> None:
    global _DB_PATH, _DB_BACKEND, _DATABASE_URL
    _DB_PATH = cfg.DB_PATH
    _DB_BACKEND = (getattr(cfg, "DB_BACKEND", "sqlite") or "sqlite").strip().lower()
    _DATABASE_URL = (getattr(cfg, "DATABASE_URL", "") or "").strip()


def _replace_qmark_params(sql: str) -> str:
    out = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _sqlite_sql_to_postgres(sql: str) -> str:
    rewritten = sql
    rewritten = re.sub(r"\bdatetime\s*\(\s*'now'\s*\)", "CURRENT_TIMESTAMP", rewritten, flags=re.IGNORECASE)
    rewritten = re.sub(r"\blast_insert_rowid\s*\(\s*\)", "LASTVAL()", rewritten, flags=re.IGNORECASE)
    if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+", rewritten, flags=re.IGNORECASE):
        rewritten = re.sub(
            r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\s+",
            "INSERT INTO ",
            rewritten,
            count=1,
            flags=re.IGNORECASE,
        )
        stripped = rewritten.rstrip()
        suffix = ";" if stripped.endswith(";") else ""
        if suffix:
            stripped = stripped[:-1].rstrip()
        rewritten = f"{stripped} ON CONFLICT DO NOTHING{suffix}"
    rewritten = _replace_qmark_params(rewritten)
    rewritten = re.sub(
        r"(?i)\b([a-z_][\w\.]*)\s*=\s*(%s|'(?:''|[^'])*')\s+COLLATE\s+NOCASE\b",
        r"LOWER(\1) = LOWER(\2)",
        rewritten,
    )
    rewritten = re.sub(r"\bCOLLATE\s+NOCASE\b", "", rewritten, flags=re.IGNORECASE)
    return rewritten


class _PgCompatCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    def execute(self, sql: str, params: Any = None):
        self._cursor.execute(_sqlite_sql_to_postgres(sql), params or ())
        return self

    def executemany(self, sql: str, params_seq: Any):
        self._cursor.executemany(_sqlite_sql_to_postgres(sql), params_seq)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def close(self) -> None:
        self._cursor.close()

    @property
    def lastrowid(self):
        row = self._cursor.connection.cursor().execute("SELECT LASTVAL() AS id").fetchone()
        return int(row["id"]) if row else None


class _PgCompatConnection:
    def __init__(self, conn: Any):
        self._conn = conn

    def cursor(self):
        return _PgCompatCursor(self._conn.cursor())

    def execute(self, sql: str, params: Any = None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def get_connection() -> Any:
    if _DB_BACKEND == "postgres":
        if not _DATABASE_URL:
            raise RuntimeError("NOTESTACK_DB_BACKEND=postgres requires DATABASE_URL")
        if psycopg is None or dict_row is None:
            raise RuntimeError("psycopg is required for PostgreSQL backend")
        raw_conn = psycopg.connect(_DATABASE_URL, row_factory=dict_row)
        return _PgCompatConnection(raw_conn)

    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize_db() -> None:
    if _DB_BACKEND == "postgres":
        _initialize_postgres_db()
        return

    conn = get_connection()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
            email       TEXT NOT NULL COLLATE NOCASE,
            password    TEXT NOT NULL,
            sso_subject TEXT UNIQUE,
            is_admin    INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS api_tokens (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token       TEXT NOT NULL UNIQUE,
            label       TEXT NOT NULL DEFAULT 'desktop',
            created_at  TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS folders (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            parent_id   INTEGER REFERENCES folders(id) ON DELETE SET NULL,
            color       TEXT DEFAULT NULL,
            sync_id     TEXT DEFAULT NULL,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, name, parent_id)
        );

        CREATE TABLE IF NOT EXISTS notes (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            folder_id         INTEGER REFERENCES folders(id) ON DELETE SET NULL,
            title             TEXT NOT NULL,
            content           TEXT NOT NULL DEFAULT '',
            is_favorite       INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
            sync_id           TEXT UNIQUE,
            client_updated_at TEXT DEFAULT NULL,
            server_rev        INTEGER NOT NULL DEFAULT 0,
            editor_type       TEXT NOT NULL DEFAULT 'lexical'
        );

        CREATE TABLE IF NOT EXISTS sync_meta (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            next_server_rev INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS tags (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name    TEXT NOT NULL COLLATE NOCASE,
            sync_id TEXT DEFAULT NULL,
            color   TEXT DEFAULT NULL,
            UNIQUE(user_id, name)
        );

        CREATE TABLE IF NOT EXISTS note_tags (
            note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (note_id, tag_id)
        );

        CREATE TABLE IF NOT EXISTS folder_tombstones (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id     TEXT NOT NULL,
            deleted_at  TEXT NOT NULL DEFAULT (datetime('now')),
            server_rev  INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        );

        CREATE TABLE IF NOT EXISTS tag_tombstones (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id     TEXT NOT NULL,
            deleted_at  TEXT NOT NULL DEFAULT (datetime('now')),
            server_rev  INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        );

        CREATE TABLE IF NOT EXISTS note_tombstones (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id     TEXT NOT NULL,
            deleted_at  TEXT NOT NULL DEFAULT (datetime('now')),
            server_rev  INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        );

        CREATE TABLE IF NOT EXISTS trash (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title       TEXT NOT NULL,
            content     TEXT NOT NULL,
            folder_name TEXT,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            tag_names   TEXT,
            sync_id     TEXT DEFAULT NULL,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            deleted_at  TEXT NOT NULL DEFAULT (datetime('now')),
            editor_type TEXT NOT NULL DEFAULT 'lexical'
        );

        CREATE TABLE IF NOT EXISTS conflicts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            note_id         INTEGER REFERENCES notes(id) ON DELETE SET NULL,
            sync_id         TEXT NOT NULL,
            server_title    TEXT NOT NULL,
            server_content  TEXT NOT NULL,
            client_title    TEXT NOT NULL,
            client_content  TEXT NOT NULL,
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            resolved        INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS sync_idempotency (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            method        TEXT NOT NULL,
            path          TEXT NOT NULL,
            idem_key      TEXT NOT NULL,
            response_json TEXT NOT NULL,
            status_code   INTEGER NOT NULL DEFAULT 200,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(user_id, method, path, idem_key)
        );
        """
    )
    conn.commit()

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_idempotency_lookup
        ON sync_idempotency(user_id, method, path, idem_key)
        """
    )
    conn.commit()
    conn.close()


def _initialize_postgres_db() -> None:
    conn = get_connection()
    statements = [
        """
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            sso_subject TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username_nocase_unique ON users ((lower(username)))",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sso_subject_unique ON users(sso_subject) WHERE sso_subject IS NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS api_tokens (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            label TEXT NOT NULL DEFAULT 'desktop',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS folders (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            parent_id BIGINT REFERENCES folders(id) ON DELETE SET NULL,
            color TEXT DEFAULT NULL,
            sync_id TEXT DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, name, parent_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            folder_id BIGINT REFERENCES folders(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            is_favorite INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            sync_id TEXT,
            client_updated_at TEXT DEFAULT NULL,
            server_rev BIGINT NOT NULL DEFAULT 0,
            editor_type TEXT NOT NULL DEFAULT 'lexical',
            UNIQUE(user_id, sync_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_meta (
            id INTEGER PRIMARY KEY,
            next_server_rev BIGINT NOT NULL DEFAULT 1,
            CHECK (id = 1)
        )
        """,
        "INSERT INTO sync_meta (id, next_server_rev) VALUES (1, 1) ON CONFLICT (id) DO NOTHING",
        """
        CREATE TABLE IF NOT EXISTS tags (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sync_id TEXT DEFAULT NULL,
            color TEXT DEFAULT NULL
        )
        """,
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_name_nocase_unique ON tags (user_id, lower(name))",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_sync_id_unique ON tags (user_id, sync_id) WHERE sync_id IS NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS note_tags (
            note_id BIGINT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
            tag_id BIGINT NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
            PRIMARY KEY (note_id, tag_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS folder_tombstones (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            server_rev BIGINT NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tag_tombstones (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            server_rev BIGINT NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS note_tombstones (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            sync_id TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            server_rev BIGINT NOT NULL DEFAULT 0,
            UNIQUE(user_id, sync_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS trash (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            folder_name TEXT,
            is_favorite INTEGER NOT NULL DEFAULT 0,
            tag_names TEXT,
            sync_id TEXT DEFAULT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            editor_type TEXT NOT NULL DEFAULT 'lexical'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS conflicts (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            note_id BIGINT REFERENCES notes(id) ON DELETE SET NULL,
            sync_id TEXT NOT NULL,
            server_title TEXT NOT NULL,
            server_content TEXT NOT NULL,
            client_title TEXT NOT NULL,
            client_content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved INTEGER NOT NULL DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sync_idempotency (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            idem_key TEXT NOT NULL,
            response_json TEXT NOT NULL,
            status_code INTEGER NOT NULL DEFAULT 200,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, method, path, idem_key)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_sync_idempotency_lookup
        ON sync_idempotency(user_id, method, path, idem_key)
        """,
    ]
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()
    conn.close()
    # SQLite migration logic below relies on PRAGMA and sqlite-specific DDL.
    # For postgres backend we only run the bootstrap statements above.
    return

    # Migrations for existing databases
    conn = get_connection()
    cur = conn.cursor()

    # Migration 0: add users.is_admin if missing
    user_cols = {row[1] for row in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "is_admin" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
    if "sso_subject" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN sso_subject TEXT")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sso_subject_unique ON users(sso_subject) WHERE sso_subject IS NOT NULL"
        )

    # Ensure at least one admin exists (bootstrap earliest user)
    admin_count = int(cur.execute(
        "SELECT COUNT(*) AS c FROM users WHERE COALESCE(is_admin, 0)=1"
    ).fetchone()["c"])
    if admin_count == 0:
        first_user = cur.execute("SELECT id FROM users ORDER BY id ASC LIMIT 1").fetchone()
        if first_user:
            cur.execute("UPDATE users SET is_admin=1 WHERE id=?", (int(first_user["id"]),))

    # Migration 1: add sync_id to folders if missing
    cols = {row[1] for row in cur.execute("PRAGMA table_info(folders)").fetchall()}
    if "sync_id" not in cols:
        cur.execute("ALTER TABLE folders ADD COLUMN sync_id TEXT DEFAULT NULL")
    conn.commit()

    # Migration 1.5: allow duplicate emails; keep username unique
    user_indexes = cur.execute("PRAGMA index_list(users)").fetchall()
    email_unique_index_present = False
    for idx in user_indexes:
        idx_name = idx[1]
        is_unique = idx[2]
        if is_unique:
            idx_cols = [r[2] for r in cur.execute(f"PRAGMA index_info({idx_name})").fetchall()]
            if idx_cols == ["email"]:
                email_unique_index_present = True
                break

    if email_unique_index_present:
        cur.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE users_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT NOT NULL UNIQUE COLLATE NOCASE,
                email       TEXT NOT NULL COLLATE NOCASE,
                password    TEXT NOT NULL,
                sso_subject TEXT UNIQUE,
                is_admin    INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO users_new (id, username, email, password, sso_subject, is_admin, created_at)
            SELECT id, username, email, password, sso_subject, COALESCE(is_admin, 0), created_at
            FROM users;
            DROP TABLE users;
            ALTER TABLE users_new RENAME TO users;
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_sso_subject_unique ON users(sso_subject) WHERE sso_subject IS NOT NULL"
    )

    # Migration 2: fix notes.sync_id unique constraint to be per-user
    # The original schema had UNIQUE(sync_id) globally; multiple users syncing from
    # the same desktop raised IntegrityError.  Recreate the table with
    # UNIQUE(user_id, sync_id) instead.
    indexes = cur.execute("PRAGMA index_list(notes)").fetchall()
    needs_fix = False
    for idx in indexes:
        idx_name = idx[1]
        is_unique = idx[2]
        if is_unique:
            idx_cols = [r[2] for r in cur.execute(f"PRAGMA index_info({idx_name})").fetchall()]
            if idx_cols == ["sync_id"]:
                needs_fix = True
                break
    if needs_fix:
        cur.executescript("""
            PRAGMA foreign_keys = OFF;
            CREATE TABLE notes_new (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                folder_id         INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                title             TEXT NOT NULL,
                content           TEXT NOT NULL DEFAULT '',
                is_favorite       INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
                sync_id           TEXT,
                client_updated_at TEXT DEFAULT NULL,
                server_rev        INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, sync_id)
            );
            INSERT OR IGNORE INTO notes_new (
                id, user_id, folder_id, title, content, is_favorite,
                created_at, updated_at, sync_id, client_updated_at, server_rev
            )
            SELECT
                id, user_id, folder_id, title, content, is_favorite,
                created_at, updated_at, sync_id, client_updated_at, 0
            FROM notes;
            DROP TABLE notes;
            ALTER TABLE notes_new RENAME TO notes;
            PRAGMA foreign_keys = ON;
        """)
        conn.commit()
    # Migration 3: server revision metadata and note revision column
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_meta (
            id              INTEGER PRIMARY KEY CHECK (id = 1),
            next_server_rev INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO sync_meta (id, next_server_rev) VALUES (1, 1)"
    )

    note_cols = {row[1] for row in conn.execute("PRAGMA table_info(notes)").fetchall()}
    tag_cols = {row[1] for row in conn.execute("PRAGMA table_info(tags)").fetchall()}
    trash_cols = {row[1] for row in conn.execute("PRAGMA table_info(trash)").fetchall()}
    if "server_rev" not in note_cols:
        conn.execute("ALTER TABLE notes ADD COLUMN server_rev INTEGER NOT NULL DEFAULT 0")
    if "sync_id" not in tag_cols:
        conn.execute("ALTER TABLE tags ADD COLUMN sync_id TEXT DEFAULT NULL")
    if "sync_id" not in trash_cols:
        conn.execute("ALTER TABLE trash ADD COLUMN sync_id TEXT DEFAULT NULL")
    if "editor_type" not in note_cols:
        conn.execute("ALTER TABLE notes ADD COLUMN editor_type TEXT NOT NULL DEFAULT 'lexical'")
    if "editor_type" not in trash_cols:
        conn.execute("ALTER TABLE trash ADD COLUMN editor_type TEXT NOT NULL DEFAULT 'lexical'")

    if "sync_id" in cols:
        conn.execute(
            """
            UPDATE folders
            SET sync_id = lower(hex(randomblob(16)))
            WHERE sync_id IS NULL OR TRIM(sync_id) = ''
            """
        )

    if "sync_id" in note_cols:
        for row in conn.execute(
            "SELECT id FROM notes WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
        ).fetchall():
            conn.execute(
                "UPDATE notes SET sync_id=? WHERE id=?",
                (str(uuid.uuid4()), int(row["id"])),
            )
    if "sync_id" in tag_cols:
        for row in conn.execute(
            "SELECT id FROM tags WHERE sync_id IS NULL OR TRIM(sync_id) = ''"
        ).fetchall():
            conn.execute(
                "UPDATE tags SET sync_id=? WHERE id=?",
                (str(uuid.uuid4()), int(row["id"])),
            )
        conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_user_sync_id_unique
            ON tags(user_id, sync_id)
            WHERE sync_id IS NOT NULL
            """
        )

    # Backfill missing revisions so every existing note has a non-zero token.
    missing_rows = conn.execute(
        "SELECT id FROM notes WHERE COALESCE(server_rev, 0) <= 0 ORDER BY updated_at ASC, id ASC"
    ).fetchall()
    for row in missing_rows:
        rev = allocate_server_rev(conn)
        conn.execute("UPDATE notes SET server_rev=? WHERE id=?", (rev, int(row["id"])))

    max_rev = int(conn.execute("SELECT COALESCE(MAX(server_rev), 0) AS m FROM notes").fetchone()["m"])
    meta = conn.execute("SELECT next_server_rev FROM sync_meta WHERE id=1").fetchone()
    next_rev = int(meta["next_server_rev"]) if meta else 1
    if next_rev <= max_rev:
        conn.execute("UPDATE sync_meta SET next_server_rev=? WHERE id=1", (max_rev + 1,))

    conn.commit()
    conn.close()


def allocate_server_rev(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT next_server_rev FROM sync_meta WHERE id=1").fetchone()
    next_rev = int(row["next_server_rev"]) if row else 1
    conn.execute("UPDATE sync_meta SET next_server_rev=? WHERE id=1", (next_rev + 1,))
    return next_rev


def _get_last_insert_id(conn, cursor: Any = None) -> int:
    if cursor is not None:
        value = getattr(cursor, "lastrowid", None)
        if value is not None:
            return int(value)

    if _DB_BACKEND == "postgres":
        row = conn.execute("SELECT LASTVAL() AS id").fetchone()
    else:
        row = conn.execute("SELECT last_insert_rowid() AS id").fetchone()
    return int(row["id"]) if row else 0


def _column_exists(conn, table: str, col: str) -> bool:
    if _DB_BACKEND == "postgres":
        row = conn.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
            LIMIT 1
            """,
            (table, col),
        ).fetchone()
        return bool(row)

    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == col for r in rows)


# ─── Color helpers (mirrors desktop) ─────────────────────────────────────────

def _normalize_color(color: Optional[str]) -> Optional[str]:
    if not color:
        return None
    v = str(color).strip()
    if not v.startswith("#"):
        v = f"#{v}"
    v = v[:7]
    return v.upper() if len(v) == 7 else None


def _generate_distinct_color(seed_index: int) -> str:
    hue = (seed_index * 0.61803398875) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.62, 0.92)
    return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"


def _next_unique_color(conn: sqlite3.Connection, table: str, user_id: int) -> str:
    rows = conn.execute(
        f"SELECT color FROM {table} WHERE user_id=? AND color IS NOT NULL AND TRIM(color)<>''",
        (user_id,),
    ).fetchall()
    used = {n for row in rows if (n := _normalize_color(row["color"]))}
    for color in DEFAULT_ENTITY_COLORS:
        n = _normalize_color(color)
        if n and n not in used:
            return n
    idx = 0
    while True:
        c = _generate_distinct_color(len(used) + idx)
        if c not in used:
            return c
        idx += 1


# ─── User helpers ─────────────────────────────────────────────────────────────

def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        "SELECT id, username, email, is_admin, created_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_id_for_api_token(token: str) -> Optional[int]:
    if not token:
        return None
    conn = get_connection()
    row = conn.execute(
        "SELECT user_id FROM api_tokens WHERE token=?",
        (token,),
    ).fetchone()
    conn.close()
    return int(row["user_id"]) if row else None


def upsert_sso_user(claims: dict) -> Optional[dict]:
    subject = str(claims.get("sub") or "").strip()
    if not subject:
        return None

    email = str(claims.get("email") or f"{subject}@nightcraft.local").strip().lower()
    username = str(claims.get("preferred_username") or claims.get("name") or f"user-{subject}").strip()
    raw_roles = claims.get("roles")
    roles = []
    if isinstance(raw_roles, str):
        roles = [raw_roles]
    elif isinstance(raw_roles, (list, tuple, set)):
        roles = [str(role) for role in raw_roles]
    normalized_roles = {role.strip().lower() for role in roles if str(role).strip()}
    is_admin = "admin" in normalized_roles or bool(claims.get("is_admin", False))

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM users WHERE sso_subject=?",
        (subject,),
    ).fetchone()
    if existing is None:
        email_match = conn.execute(
            "SELECT id FROM users WHERE LOWER(email)=LOWER(?)",
            (email,),
        ).fetchone()
        if email_match is not None:
            conn.execute(
                "UPDATE users SET username=?, email=?, sso_subject=?, is_admin=? WHERE id=?",
                (username, email, subject, 1 if is_admin else 0, int(email_match["id"])),
            )
            user_id = int(email_match["id"])
        else:
            base_username = username or f"user-{subject}"
            candidate = base_username
            suffix = 1
            while conn.execute(
                "SELECT 1 FROM users WHERE LOWER(username)=LOWER(?)",
                (candidate,),
            ).fetchone():
                candidate = f"{base_username}-{suffix}"
                suffix += 1

            conn.execute(
                "INSERT INTO users (username, email, password, sso_subject, is_admin) VALUES (?,?,?,?,?)",
                (candidate, email, generate_password_hash(uuid.uuid4().hex), subject, 1 if is_admin else 0),
            )
            user_id = _get_last_insert_id(conn)
    else:
        user_id = int(existing["id"])
        conn.execute(
            "UPDATE users SET username=?, email=?, is_admin=? WHERE id=?",
            (username, email, 1 if is_admin else 0, user_id),
        )

    conn.commit()
    row = conn.execute(
        "SELECT id, username, email, is_admin, created_at FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def is_user_admin(user_id: int) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT COALESCE(is_admin, 0) AS is_admin FROM users WHERE id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return bool(row and int(row["is_admin"]) == 1)


def get_admin_dashboard_stats() -> dict:
    conn = get_connection()
    stats = {
        "users": int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]),
        "admins": int(conn.execute("SELECT COUNT(*) AS c FROM users WHERE COALESCE(is_admin, 0)=1").fetchone()["c"]),
        "notes": int(conn.execute("SELECT COUNT(*) AS c FROM notes").fetchone()["c"]),
        "folders": int(conn.execute("SELECT COUNT(*) AS c FROM folders").fetchone()["c"]),
        "tags": int(conn.execute("SELECT COUNT(*) AS c FROM tags").fetchone()["c"]),
        "trash": int(conn.execute("SELECT COUNT(*) AS c FROM trash").fetchone()["c"]),
        "conflicts_open": int(conn.execute("SELECT COUNT(*) AS c FROM conflicts WHERE resolved=0").fetchone()["c"]),
    }
    conn.close()
    return stats


def get_admin_user_overview() -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT u.id, u.username, u.email, COALESCE(u.is_admin, 0) AS is_admin,
                  u.created_at,
                  (SELECT COUNT(*) FROM notes n WHERE n.user_id=u.id) AS note_count,
                  (SELECT COUNT(*) FROM folders f WHERE f.user_id=u.id) AS folder_count,
                  (SELECT COUNT(*) FROM tags t WHERE t.user_id=u.id) AS tag_count,
                  (SELECT COUNT(*) FROM trash tr WHERE tr.user_id=u.id) AS trash_count,
                  (SELECT COUNT(*) FROM conflicts c WHERE c.user_id=u.id AND c.resolved=0) AS open_conflicts
           FROM users u
           ORDER BY u.created_at DESC, u.id DESC"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_user_admin(target_user_id: int, make_admin: bool) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE id=?", (target_user_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE users SET is_admin=? WHERE id=?", (1 if make_admin else 0, target_user_id))
    conn.commit()
    conn.close()
    return True


def update_user_password_hash(target_user_id: int, password_hash: str) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE id=?", (target_user_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("UPDATE users SET password=? WHERE id=?", (password_hash, target_user_id))
    conn.commit()
    conn.close()
    return True


def delete_user(target_user_id: int) -> bool:
    conn = get_connection()
    row = conn.execute("SELECT id FROM users WHERE id=?", (target_user_id,)).fetchone()
    if not row:
        conn.close()
        return False
    conn.execute("DELETE FROM users WHERE id=?", (target_user_id,))
    conn.commit()
    conn.close()
    return True


# ─── Folder helpers ───────────────────────────────────────────────────────────

def get_all_folders(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, name, parent_id, color, sync_id FROM folders WHERE user_id=? ORDER BY name",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_folder(user_id: int, name: str, parent_id: Optional[int] = None,
                  color: Optional[str] = None) -> int:
    conn = get_connection()
    resolved = _normalize_color(color) if color else _next_unique_color(conn, "folders", user_id)
    sync_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO folders (user_id, name, parent_id, color, sync_id) VALUES (?,?,?,?,?)",
        (user_id, name.strip(), parent_id, resolved, sync_id),
    )
    conn.commit()
    row = {"id": _get_last_insert_id(conn)}
    conn.close()
    return int(row["id"])


def update_folder(user_id: int, folder_id: int, name: Optional[str] = None,
                  color: Optional[str] = None, parent_id: Optional[int] = None) -> bool:
    conn = get_connection()
    fields, params = [], []
    if name is not None:
        fields.append("name=?"); params.append(name.strip())
    if color is not None:
        fields.append("color=?"); params.append(_normalize_color(color))
    if parent_id is not None:
        fields.append("parent_id=?"); params.append(parent_id)
    if not fields:
        conn.close(); return False
    params += [user_id, folder_id]
    conn.execute(f"UPDATE folders SET {', '.join(fields)} WHERE user_id=? AND id=?", params)
    conn.commit(); conn.close(); return True


def delete_folder(user_id: int, folder_id: int) -> None:
    conn = get_connection()
    _delete_folder_row(conn, user_id, folder_id, create_tombstone=True)
    conn.commit(); conn.close()


def upsert_folder_by_sync_id(user_id: int, sync_id: str, name: str,
                              color: Optional[str] = None,
                              parent_sync_id: Optional[str] = None) -> int:
    """Create or update a folder by its desktop sync_id. Returns server folder_id."""
    conn = get_connection()
    try:
        tombstone = conn.execute(
            "SELECT 1 FROM folder_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, sync_id),
        ).fetchone()
        if tombstone:
            return 0

        # Resolve parent_sync_id → server folder_id (parent must already exist)
        parent_id: Optional[int] = None
        if parent_sync_id:
            parent_row = conn.execute(
                "SELECT id FROM folders WHERE sync_id=? AND user_id=?",
                (parent_sync_id, user_id),
            ).fetchone()
            if parent_row:
                parent_id = int(parent_row["id"])

        # Check if folder already exists by sync_id
        existing = conn.execute(
            "SELECT id FROM folders WHERE sync_id=? AND user_id=?", (sync_id, user_id)
        ).fetchone()
        if existing:
            folder_id = int(existing["id"])
            conn.execute(
                "UPDATE folders SET name=?, color=?, parent_id=? WHERE id=?",
                (name.strip(), color, parent_id, folder_id),
            )
            conn.commit()
            return folder_id

        # Check if folder with same name + same parent exists — adopt it
        if parent_id is not None:
            same_name = conn.execute(
                "SELECT id FROM folders WHERE user_id=? AND name=? AND parent_id=?",
                (user_id, name.strip(), parent_id),
            ).fetchone()
        else:
            same_name = conn.execute(
                "SELECT id FROM folders WHERE user_id=? AND name=? AND parent_id IS NULL",
                (user_id, name.strip()),
            ).fetchone()
        if same_name:
            folder_id = int(same_name["id"])
            conn.execute(
                "UPDATE folders SET sync_id=?, color=?, parent_id=? WHERE id=?",
                (sync_id, color, parent_id, folder_id),
            )
            conn.commit()
            return folder_id

        # Create new folder
        resolved = _normalize_color(color) if color else _next_unique_color(conn, "folders", user_id)
        conn.execute(
            "INSERT INTO folders (user_id, name, color, sync_id, parent_id) VALUES (?,?,?,?,?)",
            (user_id, name.strip(), resolved, sync_id, parent_id),
        )
        folder_id = _get_last_insert_id(conn)
        conn.commit()
        return folder_id
    finally:
        conn.close()


# ─── Tag helpers ──────────────────────────────────────────────────────────────

def get_all_tags(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT t.id, t.name, t.color, t.sync_id,
                  COUNT(nt.note_id) AS note_count
           FROM tags t
           LEFT JOIN note_tags nt ON nt.tag_id = t.id
           LEFT JOIN notes n ON n.id = nt.note_id AND n.user_id = ?
           WHERE t.user_id=?
           GROUP BY t.id
           ORDER BY t.name""",
        (user_id, user_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _ensure_tag(conn: sqlite3.Connection, user_id: int, name: str) -> int:
    normalized = name.strip().lower().lstrip("#")
    row = conn.execute("SELECT id FROM tags WHERE user_id=? AND name=?", (user_id, normalized)).fetchone()
    if row:
        return int(row["id"])
    color = _next_unique_color(conn, "tags", user_id)
    conn.execute(
        "INSERT INTO tags (user_id, name, color, sync_id) VALUES (?,?,?,?)",
        (user_id, normalized, color, str(uuid.uuid4())),
    )
    row = {"id": _get_last_insert_id(conn)}
    return int(row["id"])


def upsert_tag_by_sync_id(user_id: int, sync_id: str, name: str, color: Optional[str] = None) -> int:
    normalized_sync_id = sync_id.strip()
    normalized = name.strip().lower().lstrip("#")
    if not normalized or not normalized_sync_id:
        return 0

    conn = get_connection()
    try:
        tombstone = conn.execute(
            "SELECT 1 FROM tag_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if tombstone:
            return 0

        row = conn.execute(
            "SELECT id FROM tags WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        normalized_color = _normalize_color(color) if color else None
        if row:
            tag_id = int(row["id"])
            existing_color = conn.execute(
                "SELECT color FROM tags WHERE user_id=? AND id=?",
                (user_id, tag_id),
            ).fetchone()["color"]
            conn.execute(
                "UPDATE tags SET name=?, color=? WHERE user_id=? AND id=?",
                (normalized, normalized_color or existing_color, user_id, tag_id),
            )
            conn.commit()
            return tag_id

        row = conn.execute(
            "SELECT id, color FROM tags WHERE user_id=? AND name=?",
            (user_id, normalized),
        ).fetchone()
        if row:
            tag_id = int(row["id"])
            conn.execute(
                "UPDATE tags SET sync_id=?, color=? WHERE user_id=? AND id=?",
                (normalized_sync_id, normalized_color or row["color"], user_id, tag_id),
            )
            conn.commit()
            return tag_id

        resolved = normalized_color or _next_unique_color(conn, "tags", user_id)
        conn.execute(
            "INSERT INTO tags (user_id, name, color, sync_id) VALUES (?,?,?,?)",
            (user_id, normalized, resolved, normalized_sync_id),
        )
        conn.commit()
        return _get_last_insert_id(conn)
    finally:
        conn.close()


def update_tag(user_id: int, tag_id: int, name: Optional[str] = None,
               color: Optional[str] = None) -> bool:
    conn = get_connection()
    fields, params = [], []
    if name is not None:
        fields.append("name=?"); params.append(name.strip().lower().lstrip("#"))
    if color is not None:
        fields.append("color=?"); params.append(_normalize_color(color))
    if not fields:
        conn.close(); return False
    params += [user_id, tag_id]
    conn.execute(f"UPDATE tags SET {', '.join(fields)} WHERE user_id=? AND id=?", params)
    conn.commit(); conn.close(); return True


def delete_tag(user_id: int, tag_id: int) -> None:
    conn = get_connection()
    _delete_tag_row(conn, user_id, tag_id, create_tombstone=True)
    conn.commit(); conn.close()


def get_folder_tombstones_since(user_id: int, since_rev: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT sync_id, deleted_at, server_rev
           FROM folder_tombstones
           WHERE user_id=? AND server_rev > ?
           ORDER BY server_rev ASC""",
        (user_id, int(since_rev or 0)),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tag_tombstones_since(user_id: int, since_rev: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT sync_id, deleted_at, server_rev
           FROM tag_tombstones
           WHERE user_id=? AND server_rev > ?
           ORDER BY server_rev ASC""",
        (user_id, int(since_rev or 0)),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_note_tombstones_since(user_id: int, since_rev: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        """SELECT sync_id, deleted_at, server_rev
           FROM note_tombstones
           WHERE user_id=? AND server_rev > ?
           ORDER BY server_rev ASC""",
        (user_id, int(since_rev or 0)),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def apply_folder_tombstone(user_id: int, sync_id: str) -> bool:
    normalized_sync_id = (sync_id or "").strip()
    if not normalized_sync_id:
        return False
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM folder_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if existing:
            return False
        row = conn.execute(
            "SELECT id FROM folders WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if row:
            _delete_folder_row(conn, user_id, int(row["id"]), create_tombstone=False)
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT INTO folder_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, normalized_sync_id, server_rev),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def apply_tag_tombstone(user_id: int, sync_id: str) -> bool:
    normalized_sync_id = (sync_id or "").strip()
    if not normalized_sync_id:
        return False
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM tag_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if existing:
            return False
        row = conn.execute(
            "SELECT id FROM tags WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if row:
            _delete_tag_row(conn, user_id, int(row["id"]), create_tombstone=False)
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT INTO tag_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, normalized_sync_id, server_rev),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def apply_note_tombstone(user_id: int, sync_id: str) -> bool:
    normalized_sync_id = (sync_id or "").strip()
    if not normalized_sync_id:
        return False
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM note_tombstones WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        ).fetchone()
        if existing:
            return False
        note = conn.execute(
            """SELECT n.*, f.name AS folder_name,
                      COALESCE(
                        (SELECT GROUP_CONCAT(t.name, ',')
                         FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                         WHERE nt.note_id=n.id), ''
                      ) AS tags
               FROM notes n LEFT JOIN folders f ON f.id=n.folder_id
               WHERE n.user_id=? AND n.sync_id=?""",
            (user_id, normalized_sync_id),
        ).fetchone()
        if note:
            conn.execute(
                """INSERT INTO trash (user_id, title, content, folder_name, is_favorite, tag_names, sync_id, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    user_id,
                    note["title"],
                    note["content"],
                    note["folder_name"],
                    note["is_favorite"],
                    note["tags"],
                    note["sync_id"],
                    note["created_at"],
                    note["updated_at"],
                ),
            )
        conn.execute(
            "DELETE FROM notes WHERE user_id=? AND sync_id=?",
            (user_id, normalized_sync_id),
        )
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT INTO note_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, normalized_sync_id, server_rev),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _delete_folder_row(conn: sqlite3.Connection, user_id: int, folder_id: int, *, create_tombstone: bool) -> None:
    row = conn.execute(
        "SELECT sync_id FROM folders WHERE user_id=? AND id=?",
        (user_id, folder_id),
    ).fetchone()
    if not row:
        return
    sync_id = (row["sync_id"] or "").strip()
    conn.execute("DELETE FROM folders WHERE user_id=? AND id=?", (user_id, folder_id))
    if create_tombstone and sync_id:
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT OR IGNORE INTO folder_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, sync_id, server_rev),
        )


def _delete_tag_row(conn: sqlite3.Connection, user_id: int, tag_id: int, *, create_tombstone: bool) -> None:
    row = conn.execute(
        "SELECT sync_id FROM tags WHERE user_id=? AND id=?",
        (user_id, tag_id),
    ).fetchone()
    sync_id = (row["sync_id"] or "").strip() if row else ""
    conn.execute("DELETE FROM tags WHERE user_id=? AND id=?", (user_id, tag_id))
    if create_tombstone and sync_id:
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT OR IGNORE INTO tag_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, sync_id, server_rev),
        )


# ─── Note helpers ─────────────────────────────────────────────────────────────

def get_notes(user_id: int, folder_id: Optional[int] = None, tag_id: Optional[int] = None,
              keyword: Optional[str] = None, favorites_only: bool = False,
              sort: str = "newest", limit: int = 200, offset: int = 0,
              date_filter: Optional[str] = None) -> list[dict]:
    conn = get_connection()
    conditions = ["n.user_id=?"]
    params: list = [user_id]

    if folder_id is not None:
        conditions.append("n.folder_id=?"); params.append(folder_id)
    if tag_id is not None:
        conditions.append("EXISTS(SELECT 1 FROM note_tags nt WHERE nt.note_id=n.id AND nt.tag_id=?)")
        params.append(tag_id)
    if favorites_only:
        conditions.append("n.is_favorite=1")
    if keyword:
        kw = f"%{keyword}%"
        conditions.append("(n.title LIKE ? OR n.content LIKE ?)")
        params += [kw, kw]
    if date_filter:
        conditions.append("DATE(n.updated_at) = ?")
        params.append(date_filter)

    order = {"newest": "n.updated_at DESC", "oldest": "n.created_at ASC",
             "alpha": "n.title ASC"}.get(sort, "n.updated_at DESC")

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT n.id, n.title, n.is_favorite, n.created_at, n.updated_at, n.folder_id,
                   n.sync_id, f.name AS folder_name, f.color AS folder_color,
                                     n.content AS content, COALESCE(n.editor_type, 'lexical') AS editor_type,
                   COALESCE(
                     (SELECT GROUP_CONCAT(t.name, ',')
                      FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                      WHERE nt.note_id=n.id), ''
                   ) AS tags
            FROM notes n
            LEFT JOIN folders f ON f.id = n.folder_id
            WHERE {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_trash_notes(user_id: int, keyword: Optional[str] = None,
                    sort: str = "newest", limit: int = 200,
                    offset: int = 0) -> list[dict]:
    conn = get_connection()
    conditions = ["user_id=?"]
    params: list = [user_id]

    if keyword:
        kw = f"%{keyword}%"
        conditions.append("(title LIKE ? OR content LIKE ?)")
        params += [kw, kw]

    order = {
        "newest": "deleted_at DESC",
        "oldest": "deleted_at ASC",
        "alpha": "title ASC",
    }.get(sort, "deleted_at DESC")

    where = " AND ".join(conditions)
    rows = conn.execute(
        f"""SELECT id, title, content, is_favorite, created_at, updated_at,
                   deleted_at, folder_name, COALESCE(tag_names, '') AS tags,
                   COALESCE(editor_type, 'lexical') AS editor_type
            FROM trash
            WHERE {where}
            ORDER BY {order}
            LIMIT ? OFFSET ?""",
        params + [limit, offset],
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_note(user_id: int, note_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute(
        """SELECT n.*, f.name AS folder_name,
                  COALESCE(
                    (SELECT GROUP_CONCAT(t.name, ',')
                     FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                     WHERE nt.note_id=n.id), ''
                  ) AS tags
           FROM notes n
           LEFT JOIN folders f ON f.id = n.folder_id
           WHERE n.user_id=? AND n.id=?""",
        (user_id, note_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def create_note(user_id: int, title: str, content: str = "",
                folder_id: Optional[int] = None, is_favorite: bool = False,
                tag_names: Optional[list[str]] = None,
                sync_id: Optional[str] = None,
                client_updated_at: Optional[str] = None,
                editor_type: str = 'lexical') -> int:
    conn = get_connection()
    server_rev = allocate_server_rev(conn)
    note_sync_id = (sync_id or "").strip() or str(uuid.uuid4())
    safe_editor_type = 'lexical' if editor_type in ('tui', 'lexical') else 'lexical'
    conn.execute(
        """INSERT INTO notes (
               user_id, folder_id, title, content, is_favorite, sync_id, client_updated_at, server_rev, editor_type
           ) VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, folder_id, title.strip(), content, int(is_favorite),
         note_sync_id, client_updated_at, server_rev, safe_editor_type),
    )
    conn.execute(
        "DELETE FROM note_tombstones WHERE user_id=? AND sync_id=?",
        (user_id, note_sync_id),
    )
    note_id = _get_last_insert_id(conn)
    if tag_names:
        for tag_name in tag_names:
            tag_id = _ensure_tag(conn, user_id, tag_name)
            conn.execute(
                "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                (note_id, tag_id),
            )
    conn.commit(); conn.close()
    return note_id


def update_note(user_id: int, note_id: int, title: Optional[str] = None,
                content: Optional[str] = None, folder_id: Optional[int] = None,
                is_favorite: Optional[bool] = None, tag_names: Optional[list[str]] = None,
                client_updated_at: Optional[str] = None,
                editor_type: Optional[str] = None) -> bool:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, sync_id FROM notes WHERE user_id=? AND id=?",
            (user_id, note_id),
        ).fetchone()
        if not row:
            return False

        server_rev = allocate_server_rev(conn)
        fields = ["updated_at=datetime('now')", "server_rev=?"]
        params = [server_rev]
        if not (row["sync_id"] or "").strip():
            fields.append("sync_id=?")
            params.append(str(uuid.uuid4()))
        if title is not None:
            fields.append("title=?"); params.append(title.strip())
        if content is not None:
            fields.append("content=?"); params.append(content)
        if folder_id is not None:
            fields.append("folder_id=?"); params.append(folder_id)
        if is_favorite is not None:
            fields.append("is_favorite=?"); params.append(int(is_favorite))
        if client_updated_at is not None:
            fields.append("client_updated_at=?"); params.append(client_updated_at)
        if editor_type is not None and editor_type in ('tui', 'lexical'):
            fields.append("editor_type=?"); params.append('lexical')
        params += [user_id, note_id]
        conn.execute(f"UPDATE notes SET {', '.join(fields)} WHERE user_id=? AND id=?", params)
        if row["sync_id"]:
            conn.execute(
                "DELETE FROM note_tombstones WHERE user_id=? AND sync_id=?",
                (user_id, row["sync_id"]),
            )

        if tag_names is not None:
            conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
            for tag_name in tag_names:
                tag_id = _ensure_tag(conn, user_id, tag_name)
                conn.execute(
                    "INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                    (note_id, tag_id),
                )

        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_note(user_id: int, note_id: int) -> bool:
    conn = get_connection()
    note = conn.execute(
        """SELECT n.*, f.name AS folder_name,
                  COALESCE(
                    (SELECT GROUP_CONCAT(t.name, ',')
                     FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                     WHERE nt.note_id=n.id), ''
                  ) AS tags
           FROM notes n LEFT JOIN folders f ON f.id=n.folder_id
           WHERE n.user_id=? AND n.id=?""",
        (user_id, note_id),
    ).fetchone()
    if not note:
        conn.close(); return False
    conn.execute(
        """INSERT INTO trash (user_id, title, content, folder_name, is_favorite, tag_names, sync_id, created_at, updated_at, editor_type)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (user_id, note["title"], note["content"], note["folder_name"],
         note["is_favorite"], note["tags"], note["sync_id"], note["created_at"], note["updated_at"],
         note["editor_type"] if "editor_type" in note.keys() else "lexical"),
    )
    sync_id = (note["sync_id"] or "").strip()
    if sync_id:
        server_rev = allocate_server_rev(conn)
        conn.execute(
            "INSERT OR IGNORE INTO note_tombstones (user_id, sync_id, server_rev) VALUES (?,?,?)",
            (user_id, sync_id, server_rev),
        )
    conn.execute("DELETE FROM notes WHERE user_id=? AND id=?", (user_id, note_id))
    conn.commit(); conn.close(); return True


# ─── Sync helpers ─────────────────────────────────────────────────────────────

def get_notes_since(user_id: int, since_rev: int) -> list[dict]:
    """Return all notes with server_rev > since_rev."""
    since_rev = int(since_rev or 0)
    conn = get_connection()
    rows = conn.execute(
                """SELECT n.*, f.name AS folder_name, f.sync_id AS folder_sync_id, f.color AS folder_color,
                  COALESCE(
                    (SELECT GROUP_CONCAT(t.name, ',')
                     FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                     WHERE nt.note_id=n.id), ''
                                    ) AS tags,
                                    COALESCE(
                                        (SELECT GROUP_CONCAT(t.sync_id, ',')
                                         FROM tags t JOIN note_tags nt ON nt.tag_id=t.id
                                         WHERE nt.note_id=n.id), ''
                                    ) AS tag_sync_ids
           FROM notes n LEFT JOIN folders f ON f.id=n.folder_id
           WHERE n.user_id=? AND n.server_rev > ?
           ORDER BY n.server_rev ASC""",
        (user_id, since_rev),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_max_server_rev(user_id: int) -> int:
    conn = get_connection()
    row = conn.execute(
        """
        SELECT MAX(max_rev) AS max_rev
        FROM (
            SELECT COALESCE(MAX(server_rev), 0) AS max_rev FROM notes WHERE user_id=?
            UNION ALL
            SELECT COALESCE(MAX(server_rev), 0) AS max_rev FROM folder_tombstones WHERE user_id=?
            UNION ALL
            SELECT COALESCE(MAX(server_rev), 0) AS max_rev FROM tag_tombstones WHERE user_id=?
            UNION ALL
            SELECT COALESCE(MAX(server_rev), 0) AS max_rev FROM note_tombstones WHERE user_id=?
        ) revs
        """,
        (user_id, user_id, user_id, user_id),
    ).fetchone()
    conn.close()
    return int(row["max_rev"] if row else 0)


def get_unresolved_conflicts(user_id: int) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM conflicts WHERE user_id=? AND resolved=0 ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_conflict(user_id: int, conflict_id: int,
                     resolved_title: str, resolved_content: str) -> bool:
    conn = get_connection()
    conflict = conn.execute(
        "SELECT * FROM conflicts WHERE user_id=? AND id=? AND resolved=0",
        (user_id, conflict_id),
    ).fetchone()
    if not conflict:
        conn.close(); return False

    if conflict["note_id"]:
        server_rev = allocate_server_rev(conn)
        conn.execute(
            """UPDATE notes
               SET title=?, content=?, updated_at=datetime('now'),
                   client_updated_at=datetime('now'), server_rev=?
               WHERE id=? AND user_id=?""",
            (resolved_title, resolved_content, server_rev, conflict["note_id"], user_id),
        )
    conn.execute(
        "UPDATE conflicts SET resolved=1 WHERE id=?",
        (conflict_id,),
    )
    conn.commit(); conn.close(); return True


# ─── Full-backup export / import ──────────────────────────────────────────────

BACKUP_VERSION = "1"


def _folder_depth(folder_id: int, folder_map: dict) -> int:
    """Count ancestors of *folder_id* using the in-memory *folder_map*."""
    depth = 0
    current = folder_map[folder_id]["parent_id"]
    visited: set[int] = set()
    while current is not None:
        if current in visited:
            break
        visited.add(current)
        depth += 1
        current = folder_map[current]["parent_id"]
    return depth


def _rel_folder_path(folder_id: int, folder_map: dict) -> str:
    """Build slash-joined path WITHOUT any app-specific prefix."""
    segments: list[str] = []
    current: int | None = folder_id
    visited: set[int] = set()
    while current is not None:
        if current in visited:
            break
        visited.add(current)
        f = folder_map[current]
        segments.append(f["name"])
        current = f["parent_id"]
    segments.reverse()
    return "/".join(segments)


def _ensure_folder_path(user_id: int, path: str, conn: sqlite3.Connection) -> int | None:
    """Create folder hierarchy *path* (slash-separated).
    
    Returns the leaf folder_id, or None for an empty path.
    """
    parts = [p.strip() for p in path.strip("/").split("/") if p.strip()]
    if not parts:
        return None
    parent_id: int | None = None
    leaf_id: int | None = None
    for segment in parts:
        if parent_id is None:
            row = conn.execute(
                "SELECT id FROM folders WHERE user_id=? AND name=? AND parent_id IS NULL",
                (user_id, segment)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM folders WHERE user_id=? AND name=? AND parent_id=?",
                (user_id, segment, parent_id)
            ).fetchone()
        if row:
            leaf_id = int(row["id"])
        else:
            seg_color = _next_unique_color(conn, "folders", user_id)
            cur = conn.execute(
                "INSERT INTO folders (user_id, name, parent_id, color) VALUES (?,?,?,?)",
                (user_id, segment, parent_id, seg_color),
            )
            leaf_id = _get_last_insert_id(conn, cur)
        parent_id = leaf_id
    return leaf_id


def export_user_backup(user_id: int) -> list[str]:
    """Export user's notes, folders, tags as JSONL lines.
    
    Format compatible with desktop app export, but excludes last_accessed_at
    (per-user reading history) to avoid cross-platform conflicts.
    
    Line ordering: meta → folders (parents before children) → tags → notes.
    """
    conn = get_connection()
    lines: list[str] = []
    
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines.append(json.dumps(
        {"type": "meta", "version": BACKUP_VERSION, "app": "NoteStack", "exported_at": now},
        ensure_ascii=False,
    ))
    
    # ── Folders ──────────────────────────────────────────────────────────────
    folder_rows = conn.execute(
        "SELECT id, name, parent_id, color, created_at FROM folders WHERE user_id=? ORDER BY id",
        (user_id,)
    ).fetchall()
    folder_map: dict[int, dict] = {int(r["id"]): dict(r) for r in folder_rows}
    sorted_ids = sorted(folder_map.keys(), key=lambda fid: _folder_depth(fid, folder_map))
    for fid in sorted_ids:
        f = folder_map[fid]
        lines.append(json.dumps(
            {
                "type":       "folder",
                "path":       _rel_folder_path(fid, folder_map),
                "color":      f["color"],
                "created_at": f["created_at"],
            },
            ensure_ascii=False,
        ))
    
    # ── Tags ─────────────────────────────────────────────────────────────────
    for t in conn.execute(
        "SELECT name, color FROM tags WHERE user_id=? ORDER BY name",
        (user_id,)
    ).fetchall():
        lines.append(json.dumps(
            {"type": "tag", "name": t["name"], "color": t["color"]},
            ensure_ascii=False,
        ))
    
    # ── Notes ────────────────────────────────────────────────────────────────
    note_rows = conn.execute(
        """SELECT id, title, content, folder_id, is_favorite, sync_id, 
                  created_at, updated_at
           FROM notes
           WHERE user_id=?
           ORDER BY created_at""",
        (user_id,)
    ).fetchall()
    for row in note_rows:
        folder_id = row["folder_id"]
        if folder_id and folder_id in folder_map:
            fp = _rel_folder_path(int(folder_id), folder_map)
        else:
            fp = ""
        tags = [
            t["name"]
            for t in conn.execute(
                """SELECT t.name FROM tags t
                   JOIN note_tags nt ON nt.tag_id=t.id
                   WHERE nt.note_id=? AND t.user_id=? ORDER BY t.name""",
                (row["id"], user_id),
            ).fetchall()
        ]
        lines.append(json.dumps(
            {
                "type":        "note",
                "title":       row["title"],
                "content":     row["content"],
                "folder_path": fp,
                "tags":        tags,
                "is_favorite": bool(row["is_favorite"]),
                "sync_id":     row["sync_id"],
                "created_at":  row["created_at"],
                "updated_at":  row["updated_at"],
            },
            ensure_ascii=False,
        ))
    
    conn.close()
    return lines


def import_user_backup(user_id: int, lines: list[str]) -> dict:
    """Restore a JSONL backup into user's library.
    
    Matching strategy (in order):
      1. Notes are matched by *sync_id* (if present).
      2. Then by *title + folder_path*.
    Matched notes are **updated** with the backup's content/timestamps.
    Unmatched notes are inserted as new.
    Folders and tags are created if missing.
    
    Returns a stats dict: {folders_created, tags_created, notes_added, notes_updated}.
    """
    records: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    
    conn = get_connection()
    stats = {"folders_created": 0, "tags_created": 0, "notes_added": 0, "notes_updated": 0}
    
    # ── Pass 1: folders ───────────────────────────────────────────────────────
    for r in records:
        if r.get("type") != "folder":
            continue
        path = (r.get("path") or "").strip()
        if not path:
            continue
        fid = _ensure_folder_path(user_id, path, conn)
        if fid:
            stats["folders_created"] += 1
    
    # ── Pass 2: tags ──────────────────────────────────────────────────────────
    for r in records:
        if r.get("type") != "tag":
            continue
        name = (r.get("name") or "").strip().lower()
        if not name:
            continue
        existing = conn.execute(
            "SELECT id, color FROM tags WHERE user_id=? AND LOWER(name)=LOWER(?)",
            (user_id, name)
        ).fetchone()
        if existing:
            if r.get("color") and not existing["color"]:
                conn.execute("UPDATE tags SET color=? WHERE id=?", (r["color"], existing["id"]))
        else:
            tag_color = r.get("color") or _next_unique_color(conn, "tags", user_id)
            conn.execute(
                "INSERT INTO tags (user_id, name, color) VALUES (?,?,?)",
                (user_id, name, tag_color)
            )
            stats["tags_created"] += 1
    
    # ── Pass 3: notes ─────────────────────────────────────────────────────────
    for r in records:
        if r.get("type") != "note":
            continue
        title = (r.get("title") or "").strip()
        content = r.get("content") or ""
        if not title:
            continue
        
        folder_path = (r.get("folder_path") or "").strip()
        folder_id: int | None = None
        if folder_path:
            folder_id = _ensure_folder_path(user_id, folder_path, conn)
        
        sync_id = (r.get("sync_id") or "").strip() or None
        is_favorite = 1 if r.get("is_favorite") else 0
        created_at = r.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        updated_at = r.get("updated_at") or created_at
        tags: list[str] = [str(t).strip().lower() for t in (r.get("tags") or []) if str(t).strip()]
        
        # Match by sync_id first
        existing = None
        if sync_id:
            existing = conn.execute(
                "SELECT id FROM notes WHERE user_id=? AND sync_id=?",
                (user_id, sync_id)
            ).fetchone()
        # Fall back to title + folder
        if not existing:
            if folder_id is not None:
                existing = conn.execute(
                    "SELECT id FROM notes WHERE user_id=? AND title=? AND folder_id=?",
                    (user_id, title, folder_id)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM notes WHERE user_id=? AND title=? AND folder_id IS NULL",
                    (user_id, title)
                ).fetchone()
        
        if existing:
            note_id = int(existing["id"])
            server_rev = allocate_server_rev(conn)
            conn.execute(
                """UPDATE notes
                   SET title=?, content=?, folder_id=?, is_favorite=?,
                       sync_id=COALESCE(sync_id, ?),
                       created_at=?, updated_at=?, server_rev=?
                   WHERE id=? AND user_id=?""",
                (title, content, folder_id, is_favorite, sync_id,
                 created_at, updated_at, server_rev, note_id, user_id),
            )
            stats["notes_updated"] += 1
        else:
            server_rev = allocate_server_rev(conn)
            note_sync_id = sync_id or str(uuid.uuid4())
            cur = conn.execute(
                """INSERT INTO notes
                   (user_id, folder_id, title, content, is_favorite, sync_id,
                    created_at, updated_at, server_rev, editor_type)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (user_id, folder_id, title, content, is_favorite, note_sync_id,
                 created_at, updated_at, server_rev, 'lexical'),
            )
            note_id = _get_last_insert_id(conn, cur)
            stats["notes_added"] += 1
        
        # Update tags
        conn.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
        for tag_name in tags:
            tag_id = _ensure_tag(conn, user_id, tag_name)
            conn.execute("INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?,?)",
                        (note_id, tag_id))
    
    conn.commit()
    conn.close()
    return stats
