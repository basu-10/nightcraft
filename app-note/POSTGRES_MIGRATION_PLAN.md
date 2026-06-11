# NoteStack PostgreSQL Migration Plan

## Goal
Migrate NoteStack (`app-note`) from SQLite-first storage to PostgreSQL while preserving API behavior, sync semantics, and SSO/session flows.

## Current status
- Phase 1 started.
- Backend configuration plumbing is added (`NOTESTACK_DB_BACKEND`, `DATABASE_URL`).
- PostgreSQL schema bootstrap path is added in `app/database.py`.
- SQLite remains default runtime backend to avoid production regressions during phased migration.

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
- Add PostgreSQL role/db provisioning for NoteStack in infra scripts.
- Add `DATABASE_URL` to `/etc/nightcraft/app-note.env` templates.
- Harden production deploy: `deploy-note.sh` requires `NOTESTACK_DB_BACKEND=postgres`, derives the default PostgreSQL URL when `DATABASE_URL` is absent, and writes the resolved URL back to `/etc/nightcraft/app-note.env`.
- Harden sync logging: write sync logs under `LOCALAPPDATA/ABasu_apps/NoteStack/sync.log`, ignore directory/file creation failures, and return an empty `/sync-log` response on read failures instead of 502.
- Provide one-time data migration script from SQLite file to PostgreSQL.
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
