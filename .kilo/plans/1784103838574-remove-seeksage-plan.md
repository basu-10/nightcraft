# Remove SeekSage completely

## Goal
Remove SeekSage ("seeksage") from the Nightcraft repo and from the server bootstrap
flow so it is never built, deployed, seeded, or routed. This includes the source app,
all production + dev orchestration, nginx routing, Postgres provisioning, the OAuth
client, and documentation. Existing live-server artifacts get manual cleanup steps.

Decisions confirmed with user:
- **Delete** the source app `app-researchAgent/seeksage/` entirely.
- Edit the **on-server bootstrap** script too (it lives in the main repo at
  `server-scripts/nightcraft-server-bootstrap.sh`, git-untracked; user will `scp` it).
- Plan includes **manual live-server cleanup** (DB, OAuth client, systemd unit, venv,
  shared dir, env file).

## Important path note
Two working trees are involved:
- **Worktree** (this session): `platform-infra/`, `dev-setup/`, `app-landing/`,
  `service-auth/`, `app-researchAgent/` — tracked files edited/committed here.
- **Main repo** (separate tree): `server-scripts/nightcraft-server-bootstrap.sh` —
  untracked; edit it at
  `/run/media/bobmarley/data/dev_work/web_dev/0 serving/ionos-server-git-connected/nightcraft/server-scripts/nightcraft-server-bootstrap.sh`
  and the user re-scp's it to the VPS. It is NOT under the worktree.

---

## 1. Delete files / directories (tracked)
- `app-researchAgent/seeksage/` — entire directory (frontend + backend, ~130 files).
- `platform-infra/prod-debian/scripts/deploy-seeksage.sh`
- `platform-infra/prod-debian/scripts/seed-seeksage-client.sh`
- `platform-infra/prod-debian/systemd/nightcraft-seeksage.service`
- `platform-infra/prod-debian/env-examples/seeksage.env.example`

If `app-researchAgent/` becomes empty after deletion, leave the empty dir (git ignores it).

## 2. Edit prod-debian orchestration scripts
- `scripts/common.sh`: remove `SEEKSAGE_SLUG` (line 20), `SEEKSAGE_SRC_DIR` (line 30),
  `SEEKSAGE_SHARED_DIR` (line 40), `SEEKSAGE_VENV_DIR` (line 49).
- `scripts/deploy-all.sh`: remove `deploy-seeksage.sh` call (line 14),
  `seed-seeksage-client.sh` call (line 24), `nightcraft-seeksage.service` restart
  (line 31) and its status line entry (line 40).
- `scripts/setup-postgres.sh`:
  - remove `SEEKSAGE_DB_NAME/USER/PASSWORD` defaults (lines 24-26);
  - remove `SEEKSAGE_ENV_FILE` (line 33);
  - remove the seeksage `_extract_database_url_from_env_file` block (lines 188-192);
  - remove `SEEKSAGE_DB_NAME/USER/PASSWORD` defaults near line 222-224;
  - remove `seeksage_db_*` passthrough vars from both `psql -v` blocks (lines 233-234
    and 248-249).
- `scripts/install-systemd.sh`: remove the `nightcraft-seeksage.service` install line
  (15) and enable line (29).
- `scripts/install-env.sh`: remove the `app-seeksage.env` / `seeksage.env.example`
  `copy_env` block (lines 80-82).
- `scripts/reset-stack.sh`:
  - remove `nightcraft-seeksage.service` from `SERVICES` array (line 87);
  - remove `${SEEKSAGE_SHARED_DIR}` (line 102) and `${SEEKSAGE_VENV_DIR}` (line 108)
    from rm lists;
  - remove `/etc/nightcraft/app-seeksage.env` (line 116) and
    `/etc/systemd/system/nightcraft-seeksage.service` (line 133) from rm lists.
- `scripts/start-all.sh`: remove `nightcraft-seeksage.service` start (line 8) and from
  status line (line 15).
- `scripts/stop-all.sh`: remove `nightcraft-seeksage.service` from status line (line 11).
- `scripts/restart-all.sh`: remove `nightcraft-seeksage.service` restart (line 7) and
  from status line (line 14).
- `scripts/status-all.sh`: remove `nightcraft-seeksage.service` from status line (line 4).
- `scripts/backup-postgres.sh`: remove `SEEKSAGE_DB_NAME` default (line 10) and its
  `pg_dump` line (line 23).

## 3. Edit Postgres SQL templates
- `postgres/create-dbs.sql`: remove `seeksage_db_name/seeksage_db_user` from the
  required-vars comment (line 7), the CREATE DATABASE `seeksage` block (lines 40-49),
  and the GRANT block (lines 75-79).
- `postgres/users-and-permissions.sql`: remove `seeksage_db_user/seeksage_db_password`
  from the required-vars comment (line 7), the CREATE ROLE block (lines 40-49), and the
  ALTER ROLE block (lines 75-79).

## 4. Edit nginx
- `nginx/nightcraft.conf`: remove `upstream app_seeksage_upstream { … }` (lines 24-27),
  the `location = /seeksage { return 301 /seeksage/; }` (lines 99-101), and the
  `location /seeksage/ { … }` proxy block (lines 175-186).

## 5. Edit dev-setup scripts
- `dev-setup/common.sh`: remove `SEEKSAGE_SRC_DIR` (line 22), `SEEKSAGE_VENV`
  (line 32), `SEEKSAGE_SHARED` (line 42).
- `dev-setup/seed-data.sh`: remove the "OAuth client: seeksage-app" `safe_seed` block
  (lines 65-71).
- `dev-setup/setup-dbs.sh`: remove `seeksage_db_user`/`seeksage_db_password` passthrough
  from both `psql -v` blocks (lines 25-26 and 40-41).
- `dev-setup/start-all.sh`: remove `ensure_dir "${SEEKSAGE_SHARED}/instance"` (line 13)
  and the `start_service "seeksage" …` line (line 89).
- `dev-setup/status.sh`: remove `"seeksage:5000:seeksage-backend"` from `SERVICES`
  array (line 14).
- `dev-setup/nightcraft-dev-setup.sh`: remove the
  `http://127.0.0.1:5000/seeksage (SeekSage)` echo line (line 160).
- `dev-setup/install-deps.sh`: remove the "app-seeksage (backend)…" block (lines 22-23).
- `dev-setup/install-env.sh`: remove the `app-seeksage.env` `copy_env` line (line 33).
- `dev-setup/readme.md`: remove seeksage rows/mentions (lines ~26, 135, 147, 174, 218).

## 6. Edit app-landing (consumer)
- `app-landing/config.py`: remove `SEEKSAGE_URL` field (line 43). It is unused in
  templates — safe to drop.
- `platform-infra/prod-debian/env-examples/landing.env.example`: remove
  `LANDING_SEEKSAGE_URL=/seeksage` (line 13).
- `app-landing/README.md`: remove the `LANDING_SEEKSAGE_URL` bullet (line 45).

## 7. Edit the on-server bootstrap script (main repo, untracked)
File: `/run/media/bobmarley/.../nightcraft/server-scripts/nightcraft-server-bootstrap.sh`
- Remove `SEEKSAGE_DB_PASSWORD="${SEEKSAGE_DB_PASSWORD:-}"` (line 45).
- Remove the `--seeksage-db-password` usage text (lines 67-68).
- Remove the `--seeksage-db-password)` parse_args case (lines 205-207).
- Remove `SEEKSAGE_DB_PASSWORD="${SEEKSAGE_DB_PASSWORD}" \` from the
  `setup-postgres` env passthrough (line 439).
(The bootstrap calls `deploy-all.sh`, which no longer references seeksage, so the build
stops once both this file and the repo `deploy-all.sh` are updated.)

## 8. Documentation cleanup (remaining `seeksage` mentions)
Update prose in:
- `platform-infra/prod-debian/README.md`
- `platform-infra/prod-debian/overview_of__production_server.md`
- `platform-infra/prod-debian/server-security-hardening-checklist.md`
- `platform-infra/prod-debian/imp_info.md`
- `service-auth/README.md` (the `/seeksage/ui` cross-app-destination note, line 77)
- `context.md` (lines 28-29)
Remove or rewrite every seeksage reference (app description, nginx route, systemd unit,
env file, port 5700, DB, OAuth client, deploy/seed/start/stop/restart script lists).

## 9. Manual live-server cleanup (run on the VPS, not in repo)
After the next bootstrap/deploy, or separately:
- Stop + disable the unit: `sudo systemctl stop nightcraft-seeksage.service &&
  sudo systemctl disable nightcraft-seeksage.service &&
  sudo rm -f /etc/systemd/system/nightcraft-seeksage.service && sudo systemctl daemon-reload`
- Remove runtime: `sudo rm -rf /runtime/venvs/seeksage-backend
  /runtime/shared/seeksage-backend /etc/nightcraft/app-seeksage.env`
- Drop DB + role (as postgres): `DROP DATABASE IF EXISTS seeksage_db;
  DROP ROLE IF EXISTS seeksage_app;`
- Revoke/delete the `seeksage-app` OAuth client + any seeksage users in the auth DB.
- Remove leftover dev pid if present: repo `.nightcraft-shared/seeksage.pid`.
- Reload nginx after the repo `nightcraft.conf` is deployed
  (`sudo nginx -t && sudo systemctl reload nginx`).

## Validation
- `grep -rin "seeksage" --include=*.sh --include=*.sql --include=*.conf --include=*.py
  --include=*.md .` returns no source/orchestration hits (docs may be intentionally
  empty of the term after step 8).
- `bash -n` on every edited shell script (common.sh, deploy-all.sh, setup-postgres.sh,
  install-systemd.sh, install-env.sh, reset-stack.sh, start/stop/restart/status-all.sh,
  backup-postgres.sh, bootstrap) — no syntax errors.
- `psql` SQL template preflight in `setup-postgres.sh` still passes
  (`\set ON_ERROR_STOP on` present, no orphan backslashes) after removing seeksage vars.
- Repo `deploy-all.sh` no longer references `deploy-seeksage.sh` or `seed-seeksage-client.sh`.
- `nginx -t` valid after removing the seeksage upstream/location blocks.
- Bootstrap dry run (`--check-only`) completes without referencing seeksage.

## Open questions / risks
- If any PR/docs reference port 5700 or `/seeksage` in prose not covered above, they are
  cosmetic — flag rather than block.
- The live `seeksage_db` may have dependent foreign keys only within itself; dropping it
  is safe. Confirm no other app's `DATABASE_URL` points at `seeksage_db`.
