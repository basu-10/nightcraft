#!/usr/bin/env python3
"""One-time migration of a NoteStack SQLite database to PostgreSQL.

This is an operational, idempotent helper used during the PostgreSQL cutover
(Phase 3 of POSTGRES_MIGRATION_PLAN.md). It is NOT part of the runtime application.

What it does
------------
1. Creates the full NoteStack schema in the target PostgreSQL database
   (reusing the application's own schema bootstrap so the two stay in lock-step).
2. Copies every row from the SQLite file into PostgreSQL, preserving primary-key
   ids so foreign-key relationships (users -> notes/folders/tags, note_edges,
   note_tags, tombstones, etc.) survive the move.
3. Resets PostgreSQL sequences to the max copied id so future inserts continue
   from the right value.
4. Is safe to re-run: rows are upserted on primary key (ON CONFLICT DO NOTHING),
   so a partial/failed run can simply be repeated.

Usage
-----
    python3 migrate_sqlite_to_postgres.py \
        --sqlite-path /path/to/notestack.db \
        --database-url postgresql://notestack_app:PASSWORD@127.0.0.1:5432/notestack_db

Environment fallbacks: NOTESTACK_DB (sqlite path) and DATABASE_URL.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import app.database as database  # noqa: E402
from app.references import initialize_edge_schema  # noqa: E402


# Tables are ordered so that referenced (parent) rows exist before the rows that
# point at them. Every table here is keyed by an explicit id we preserve.
TABLE_ORDER = [
    "users",
    "folders",
    "tags",
    "notes",
    "api_tokens",
    "note_tags",
    "note_edges",
    "folder_tombstones",
    "tag_tombstones",
    "note_tombstones",
    "trash",
    "conflicts",
    "sync_idempotency",
    "usage_events",
]


def _columns(sqlite_conn: sqlite3.Connection, table: str) -> list[str]:
    rows = sqlite_conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [row[1] for row in rows]


def _copy_table(pg_conn, sqlite_conn: sqlite3.Connection, table: str) -> int:
    cols = _columns(sqlite_conn, table)
    if not cols:
        print(f"  [skip] {table}: not present in SQLite source")
        return 0

    rows = sqlite_conn.execute(f"SELECT {', '.join(cols)} FROM {table}").fetchall()
    if not rows:
        print(f"  [ok]   {table}: 0 rows")
        return 0

    placeholders = ", ".join("?" for _ in cols)
    col_list = ", ".join(cols)
    # INSERT ... ON CONFLICT (id/pk) DO NOTHING keeps the run idempotent.
    sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING"
    copied = 0
    for row in rows:
        # row is sqlite3.Row -> tuple of values in column order.
        values = tuple(row)
        try:
            pg_conn.execute(sql, values)
            copied += 1
        except Exception as exc:  # pragma: no cover - defensive per-row guard
            print(f"  [warn] {table}: skipping row {values[:1]}: {exc}")
    pg_conn.commit()
    print(f"  [ok]   {table}: {copied}/{len(rows)} rows")
    return copied


def _reset_sequence(pg_conn, table: str) -> None:
    try:
        pg_conn.execute(
            "SELECT setval(pg_get_serial_sequence(%s, 'id'), "
            "COALESCE((SELECT MAX(id) FROM {t}), 1), true)".format(t=table),
            (table,),
        )
        pg_conn.commit()
    except Exception as exc:  # pragma: no cover - some tables may lack an id col
        print(f"  [warn] could not reset sequence for {table}: {exc}")


def _copy_sync_meta(pg_conn, sqlite_conn: sqlite3.Connection) -> None:
    try:
        row = sqlite_conn.execute(
            "SELECT id, next_server_rev FROM sync_meta WHERE id=1"
        ).fetchone()
    except sqlite3.OperationalError:
        print("  [skip] sync_meta: not present in SQLite source")
        return
    if not row:
        print("  [skip] sync_meta: empty")
        return
    pg_conn.execute(
        "INSERT INTO sync_meta (id, next_server_rev) VALUES (?, ?) "
        "ON CONFLICT (id) DO UPDATE SET next_server_rev = "
        "GREATEST(sync_meta.next_server_rev, EXCLUDED.next_server_rev)",
        (int(row[0]), int(row[1])),
    )
    pg_conn.commit()
    print(f"  [ok]   sync_meta: next_server_rev={int(row[1])}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sqlite-path",
        default=os.environ.get("NOTESTACK_DB"),
        help="Path to the legacy notestack.db SQLite file (default: $NOTESTACK_DB).",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Target PostgreSQL DATABASE_URL (default: $DATABASE_URL).",
    )
    args = parser.parse_args()

    if not args.sqlite_path:
        print("ERROR: provide --sqlite-path (or set NOTESTACK_DB).", file=sys.stderr)
        return 2
    if not os.path.isfile(args.sqlite_path):
        print(f"ERROR: SQLite file not found: {args.sqlite_path}", file=sys.stderr)
        return 2
    if not args.database_url:
        print("ERROR: provide --database-url (or set DATABASE_URL).", file=sys.stderr)
        return 2

    # Point the application's database layer at PostgreSQL.
    database._DB_BACKEND = "postgres"
    database._DATABASE_URL = args.database_url

    # Provision schema in PostgreSQL (reuses the same DDL the app uses at runtime).
    print("Initializing PostgreSQL schema...")
    database.initialize_db()
    initialize_edge_schema()

    sqlite_conn = sqlite3.connect(args.sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_conn = database.get_connection()

    try:
        print("Copying tables (idempotent; safe to re-run):")
        for table in TABLE_ORDER:
            _copy_table(pg_conn, sqlite_conn, table)
            _reset_sequence(pg_conn, table)
        _copy_sync_meta(pg_conn, sqlite_conn)
    finally:
        sqlite_conn.close()
        pg_conn.close()

    print("Migration complete. Verify parity with the PostgreSQL integration tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
