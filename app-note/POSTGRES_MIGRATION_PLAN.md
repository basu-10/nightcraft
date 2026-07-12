# NoteStack PostgreSQL Migration Plan

## Goal
Migrate NoteStack (`app-note`) from SQLite-first storage to PostgreSQL while preserving API behavior, sync semantics, and SSO/session flows.

## Current status
- Phase 1 complete: backend config (`NOTESTACK_DB_BACKEND`, `DATABASE_URL`) and
  PostgreSQL schema bootstrap live in `app/database.py`; `note_edges` schema is
  handled in `app/references.py`.
- Phase 2 complete: all SQLite-only constructs in runtime paths are covered by the
  SQL compatibility layer in `app/database.py` (`datetime('now')`, `last_insert_rowid()`,
  `INSERT OR IGNORE`, `COLLATE NOCASE`, `GROUP_CONCAT`); backend-specific tests exist.
- Phase 3 complete:
  - PostgreSQL role/db are provisioned for notestack via
    `platform-infra/prod-debian/postgres/{create-dbs,users-and-permissions}.sql`
    and `scripts/setup-postgres.sh` (wired through `nightcraft-server-bootstrap.sh`).
  - `platform-infra/prod-debian/env-examples/note.env.example` templates
    `/etc/nightcraft/app-note.env` (installed by `scripts/install-env.sh`), sets
    `NOTESTACK_DB_BACKEND=postgres`, and lets `deploy-note.sh` derive `DATABASE_URL`.
  - `deploy-note.sh` requires `NOTESTACK_DB_BACKEND=postgres` and derives/writes
    `DATABASE_URL` into `/etc/nightcraft/app-note.env`.
  - Sync logging is hardened (`app/sync_logging.py` ignores dir/file failures;
    `app/main/routes.py` `/sync-log` returns an empty body on read errors).
  - One-time data migration script: `app-note/scripts/migrate_sqlite_to_postgres.py`.
- Phase 4 (cutover) and Phase 5 (cleanup) are operational/server steps.

## Phase 1: Foundation (in progress)
- Add PostgreSQL driver dependency (`psycopg[binary]`).
- Add backend selection config (`sqlite` default, `postgres` optional).
- Add PostgreSQL bootstrap schema creation path.
- Add SQL compatibility layer for placeholder and syntax translation.
- Keep current SQLite behavior unchanged by default.

## Phase 2: Query compatibility hardening
- Convert all SQLite-only SQL constructs in runtime paths:
  - `PRAGMA` usage
  - `COLLATE NOCASE` assumptions
  - `datetime('now')` updates
  - `INSERT OR IGNORE` conflict semantics
- Replace dynamic table introspection with backend-neutral helpers.
- Add backend-specific integration tests for core CRUD and sync endpoints.

## Phase 3: Production cutover preparation
- Add PostgreSQL role/db provisioning for NoteStack in infra scripts. (DONE)
- Add `DATABASE_URL` to `/etc/nightcraft/app-note.env` templates. (DONE:
  `platform-infra/prod-debian/env-examples/note.env.example`, consumed by
  `install-env.sh`; `deploy-note.sh` derives `DATABASE_URL` when absent.)
- Harden production deploy: `deploy-note.sh` requires `NOTESTACK_DB_BACKEND=postgres`, derives the default PostgreSQL URL when `DATABASE_URL` is absent, and writes the resolved URL back to `/etc/nightcraft/app-note.env`. (DONE)
- Harden sync logging: write sync logs under `LOCALAPPDATA/ABasu_apps/NoteStack/sync.log`, ignore directory/file creation failures, and return an empty `/sync-log` response on read failures instead of 502. (DONE)
- Provide one-time data migration script from SQLite file to PostgreSQL. (DONE:
  `app-note/scripts/migrate_sqlite_to_postgres.py`.)
- Validate read/write parity against snapshot fixtures.

## Phase 4: Cutover
- Deploy postgres-backed config in staging.
- Run migrations and smoke tests (`/api`, sync push/pull/conflicts, auth flow).
- Switch production `NOTESTACK_DB_BACKEND=postgres`.
- Keep rollback path to SQLite snapshot until stable window passes.

## Phase 5: Cleanup
- Remove SQLite runtime dependency and SQLite-specific code paths.
- Remove `NOTESTACK_DB` from primary docs and env examples.
- Keep migration notes for operations/debugging only.

## Risks to watch
- Timestamp/text compatibility differences in sync conflict logic.
- Case-insensitive uniqueness behavior (`username`, `tag` names).
- Idempotency and conflict-table writes under concurrent clients.
- SQL translation edge cases where `?` appears in string literals.

## Immediate next implementation steps
1. Add backend-specific tests for user auth, notes CRUD, tag links, and tombstones.
2. Patch remaining SQL statements that rely on SQLite-only behavior.
3. Add infra SQL bootstrap for `notestack_db` + `notestack_app`.
