# Prod Debian Infrastructure

This folder is the production Linux deployment hub for Nightcraft apps.

Current target in this phase:

- `app-landing` (root product hub)
- `service-auth` (OIDC/SSO provider)
- `app-radio` (DevRadio client app, `AUTH_MODE=sso`, routed under `/devradio`)
- `app-artsy` (NEERA client app, `AUTH_MODE=sso`, routed under `/neera`)
- `app-note` (NoteStack app, shared-session auth via `service-auth`, routed under `/notestack`)
- `app-admin` (admin login handoff app)

Production routing on the server is path-based on the single host `31.70.85.89`:

- `http://31.70.85.89/` -> app-landing
- `http://31.70.85.89/auth` -> service-auth
- `http://31.70.85.89/devradio` -> app-radio
- `http://31.70.85.89/neera` -> app-artsy (Neera)
- `http://31.70.85.89/notestack` -> app-note (NoteStack)
- `http://31.70.85.89/admin` -> app-admin
- `http://31.70.85.89/platform-admin` -> app-landing (central admin hub)

All setup, deploy, seed, start, stop, and backup operations are script-driven from `platform-infra/prod-debian/scripts`.

Primary operations can be run through the single dispatcher command `serverctl` in that folder.

Deployment runs are logged on the VPS under `/var/log/nightcraft-deploy/`, and each bootstrap run appends a CSV summary to `/runtime/deploy-history.csv`.

## Single-Command Server Bootstrap

Use `server-scripts/nightcraft-server-bootstrap.sh` to run the whole flow from one command:

- validates baseline server requirements
- clones or updates repo from git
- runs env/postgres/systemd/nginx install scripts
- runs app deploy and service restart via `deploy-all.sh`

Each run creates a timestamped log in `/var/log/nightcraft-deploy/` and appends a deployment record to `/runtime/deploy-history.csv` with start time, commit, duration, and success/failure.

Recommended on the VPS: keep this script outside the checkout (for example under `/usr/local/sbin/server-scripts`) and point it at `/nightcraft-source-code`.

Example install and run:

```bash
sudo install -d -m 0755 /usr/local/sbin/server-scripts
sudo install -m 0755 /tmp/nightcraft-server-bootstrap.sh /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh
sudo /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh \
  --repo-url https://github.com/basu-10/nightcraft.git \
  --branch main \
  --target-dir /nightcraft-source-code \
  --adopt-existing
```

Useful flags:

- `--check-only` preflight only
- `--force-sync` force checkout to `origin/<branch>`
- `--overwrite-env` overwrite `/etc/nightcraft/*.env` from repo templates
- `--reset-neera-password` rotate the neera DB password and resync PostgreSQL before deploying
- `--skip-postgres`, `--skip-nginx`, `--skip-systemd`, `--skip-deploy` for partial runs
- `--run-host-setup` or `--skip-host-setup` for setup-host control

To inspect deployment history after runs:

```bash
platform-infra/prod-debian/scripts/status-deploys.sh
```

## Folder Layout

- `nginx/nightcraft.conf`: reverse proxy config for landing/auth/devradio/neera/notestack/admin
- `systemd/nightcraft-auth.service`: Gunicorn service for auth
- `systemd/nightcraft-radio.service`: Gunicorn service for radio
- `systemd/nightcraft-neera.service`: Gunicorn service for NEERA
- `systemd/nightcraft-landing.service`: Gunicorn service for landing
- `systemd/nightcraft-admin.service`: Gunicorn service for admin handoff
- `systemd/nightcraft-note.service`: Gunicorn service for NoteStack
- `postgres/users-and-permissions.sql`: role/user creation SQL
- `postgres/create-dbs.sql`: DB creation/grant SQL
- `env-examples/service-auth.env`: exact file for `/etc/nightcraft/service-auth.env`
- `env-examples/app-radio.env`: exact file for `/etc/nightcraft/app-radio.env`
- `env-examples/app-neera.env`: exact file for `/etc/nightcraft/app-neera.env`
- `env-examples/app-landing.env`: exact file for `/etc/nightcraft/app-landing.env`
- `env-examples/app-admin.env`: exact file for `/etc/nightcraft/app-admin.env`
- `env-examples/app-note.env`: exact file for `/etc/nightcraft/app-note.env`
- `env-examples/*.env.example`: alternate template variants if needed
- `scripts/setup-host.sh`: Debian package/bootstrap setup
- `scripts/setup-postgres.sh`: create postgres users + databases
- `scripts/install-nginx.sh`: install and enable nginx site
- `scripts/install-systemd.sh`: install and enable systemd units
- `scripts/install-env.sh`: install env files from `env-examples/*.env` into `/etc/nightcraft`
- `scripts/deploy-auth.sh`: release deploy for service-auth
- `scripts/deploy-radio.sh`: release deploy for app-radio
  - Keeps runtime instance data under `/runtime/shared/dev-podcast-app/instance`, including uploads and automation logs.
- `scripts/deploy-neera.sh`: release deploy for app-artsy; syncs PostgreSQL provisioning from `/etc/nightcraft/app-neera.env` before Flask setup
- `scripts/reset-neera-password.sh`: rotate neera PostgreSQL password and resync `/etc/nightcraft/app-neera.env`
- `scripts/deploy-landing.sh`: release deploy for app-landing
- `scripts/deploy-admin.sh`: release deploy for app-admin
- `scripts/deploy-note.sh`: release deploy for app-note
  - Requires `NOTESTACK_DB_BACKEND=postgres` in `/etc/nightcraft/app-note.env`.
  - If `DATABASE_URL` is absent, derives it from the default NoteStack PostgreSQL role/database/password and writes it back to `/etc/nightcraft/app-note.env`.
  - Sync logs live under `/runtime/shared/app-note/localappdata/ABasu_apps/NoteStack/sync.log`; sync-log page creation/read failures are handled without returning 502.
- `scripts/seed-auth-users.sh`: seed one service-auth user and one admin user
- `scripts/seed-auth-client.sh`: seed OAuth client/user for radio callback
- `scripts/seed-neera-client.sh`: seed OAuth client/user for neera callback
- `scripts/deploy-all.sh`: landing + auth + radio + NEERA + admin + notestack deploy + seed + restart
- `scripts/start-all.sh`: start landing + auth + radio + NEERA + admin + notestack
- `scripts/stop-all.sh`: stop landing + auth + radio + NEERA + admin + notestack
- `scripts/restart-all.sh`: restart landing + auth + radio + NEERA + admin + notestack + reload nginx
- `scripts/status-all.sh`: service status overview; `systemctl status` is non-fatal so one stopped service does not hide the rest of the stack
- `scripts/backup-postgres.sh`: logical postgres backups
- `scripts/backup-all.sh`: backup postgres + `/etc/nightcraft` + `/runtime/shared/*`
- `scripts/cleanup-releases.sh`: obsolete helper kept only to report that release pruning is no longer needed
- `scripts/reset-stack.sh`: reset app deploy state with keep-data default and explicit remove-data mode
- `scripts/serverctl`: single command dispatcher for deploy/backup/status/restart/start/stop/reset
- `scripts/status-deploys.sh`: summarize `/runtime/deploy-history.csv` into a readable deployment report

## Runtime Layout Used On Server

Apps run directly from the source checkout under `/nightcraft-source-code`:

- `/nightcraft-source-code/app-landing`
- `/nightcraft-source-code/service-auth`
- `/nightcraft-source-code/app-radio`
- `/nightcraft-source-code/app-artsy`
- `/nightcraft-source-code/app-admin`
- `/nightcraft-source-code/app-game`
- `/nightcraft-source-code/app-note`

Each app uses:

- Dedicated virtualenv under `/runtime/venvs/`
  - `/runtime/venvs/app-landing`
  - `/runtime/venvs/service-auth`
  - `/runtime/venvs/dev-podcast-app`
  - `/runtime/venvs/app-artsy`
  - `/runtime/venvs/app-admin`
  - `/runtime/venvs/app-note`
- Runtime state under `/runtime/shared/`
  - `/runtime/shared/service-auth`
  - `/runtime/shared/dev-podcast-app`, including `instance/uploads/works` and `instance/automation_logs`
  - `/runtime/shared/app-artsy`, including `instance/uploads/works`
  - `/runtime/shared/app-note`

## Expected Server Baseline

Validated against the provided host:

- Debian 12
- PostgreSQL active
- nginx active with default site
- existing runtime roots under `/runtime`

No server-side code edits are needed. Upload repo folders and run scripts.

## First-Time Setup Order

Run from your uploaded repo root on the Debian server.

1. Make scripts executable.

```bash
chmod +x platform-infra/prod-debian/scripts/*.sh
chmod +x platform-infra/prod-debian/scripts/serverctl
```

1. Install host dependencies.

```bash
sudo platform-infra/prod-debian/scripts/setup-host.sh
```

1. Prepare env files.

```bash
sudo platform-infra/prod-debian/scripts/install-env.sh
```

The command above installs these exact filenames under `/etc/nightcraft`:

- `/etc/nightcraft/service-auth.env`
- `/etc/nightcraft/app-radio.env`
- `/etc/nightcraft/app-neera.env`
- `/etc/nightcraft/app-landing.env`
- `/etc/nightcraft/app-admin.env`
- `/etc/nightcraft/app-note.env`

`install-env.sh` accepts required and optional env targets. Required services fail if no template exists; optional services keep an existing env file or skip creation when no template is present. Each target accepts a primary `*.env` template plus optional `*.env.example` fallback candidates, keeps existing files by default, normalizes CRLF line endings, and only overwrites when `OVERWRITE=1` or `--overwrite` is supplied.

Review and edit once if needed:

```bash
sudo nano /etc/nightcraft/app-landing.env
sudo nano /etc/nightcraft/service-auth.env
sudo nano /etc/nightcraft/app-radio.env
sudo nano /etc/nightcraft/app-neera.env
sudo nano /etc/nightcraft/app-admin.env
sudo nano /etc/nightcraft/app-note.env
```

1. Create DB users and databases.

`setup-postgres.sh` now provisions and grants for auth, radio, NEERA, and notestack.
For NEERA/notestack it reads `/etc/nightcraft/app-neera.env` and
`/etc/nightcraft/app-note.env`
`DATABASE_URL` values when explicit `NEERA_DB_*`/`NOTESTACK_DB_*` vars are not provided.
Existing role passwords are synchronized on each run.
The script preflights SQL templates for required `\set ON_ERROR_STOP on`, orphan backslash lines, malformed `\ gexec` spacing, and missing files before invoking psql.
It also accepts `postgresql+psycopg://`, `postgresql://`, and `postgres://` URLs and normalizes the first two forms to `postgresql+psycopg://` for SQLAlchemy/psycopg v3.

```bash
sudo AUTH_DB_PASSWORD='auth_app_db_2026_prod_secret' RADIO_DB_PASSWORD='radio_app_db_2026_prod_secret' \
  platform-infra/prod-debian/scripts/setup-postgres.sh
```

1. Install systemd units and nginx config.

```bash
sudo platform-infra/prod-debian/scripts/install-systemd.sh
sudo platform-infra/prod-debian/scripts/install-nginx.sh
```

1. Deploy app code and run seed scripts (role users + OAuth clients).

```bash
platform-infra/prod-debian/scripts/serverctl deploy
```

1. Verify status.

```bash
platform-infra/prod-debian/scripts/serverctl status
```

## Server Control Entrypoint

Run from repo root (or from `platform-infra/prod-debian/scripts` directly):

```bash
platform-infra/prod-debian/scripts/serverctl deploy
platform-infra/prod-debian/scripts/serverctl backup
platform-infra/prod-debian/scripts/serverctl status
platform-infra/prod-debian/scripts/serverctl restart
platform-infra/prod-debian/scripts/serverctl reset
```

`serverctl reset` automatically forwards `--yes` to `reset-stack.sh`. Extra flags are passed through, for example:

```bash
platform-infra/prod-debian/scripts/serverctl reset --remove-shared-data --with-postgres
```

## Minimal Required Env Values

In `/etc/nightcraft/service-auth.env`:

- `SECRET_KEY`
- `DATABASE_URL` (postgres URL for auth DB)
- `OIDC_ISSUER=http://31.70.85.89/auth`
- `PUBLIC_BASE_URL=http://31.70.85.89/auth`
- `OIDC_KEYS_DIR=/runtime/shared/service-auth/keys`

In `/etc/nightcraft/app-radio.env`:

- `FLASK_SECRET_KEY`
- `FLASK_AUTH_MODE=sso`
- `FLASK_AUTH_SERVICE_URL=http://31.70.85.89/auth`
- `FLASK_AUTHLIB_CLIENT_ID`
- `FLASK_AUTHLIB_CLIENT_SECRET`
- `FLASK_SQLALCHEMY_DATABASE_URI` (postgres URL for radio DB)

In `/etc/nightcraft/app-landing.env`:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY`
- `LANDING_AUTH_URL=/auth/login`
- `LANDING_ADMIN_URL=/platform-admin`
- `LANDING_DEVRADIO_URL=/devradio`
- `LANDING_NEERA_URL=/neera`
- `LANDING_NOTESTACK_URL=/notestack`

In `/etc/nightcraft/app-neera.env`:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY`
- `FLASK_AUTH_MODE=sso`
- `FLASK_AUTH_SERVICE_URL=http://31.70.85.89/auth`
- `FLASK_AUTHLIB_CLIENT_ID=neera-app`
- `FLASK_AUTHLIB_CLIENT_SECRET`
- `DATABASE_URL` (postgres URL for NEERA DB)

In `/etc/nightcraft/app-admin.env`:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY`
- `ADMIN_AUTH_URL=/auth/login`
- `ADMIN_RETURN_PATH=/admin`

In `/etc/nightcraft/app-note.env`:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY`
- `AUTH_MODE=sso`
- `AUTH_SERVICE_URL=http://31.70.85.89/auth`
- `SESSION_COOKIE_PATH=/notestack`
- `NOTESTACK_DB_BACKEND=postgres`
- `DATABASE_URL` (postgres URL for notestack DB)
- `LOCALAPPDATA=/runtime/shared/app-note/localappdata`

## Cross-App Auth Redirect Behavior

`service-auth` preserves post-login `next` URLs for cross-app destinations such as `/neera/me` or `/notestack/app`.
It rejects absolute URLs and open redirects, then applies `X-Forwarded-Prefix` only to auth-internal paths such as `/oauth/`, `/login`, `/register`, `/logout`, `/session/`, and `/healthz`.
This keeps app destinations intact while still allowing auth UI links to work when `/auth` is mounted behind the Nightcraft nginx prefix.

## Runtime Operations

```bash
platform-infra/prod-debian/scripts/serverctl start
platform-infra/prod-debian/scripts/serverctl stop
platform-infra/prod-debian/scripts/serverctl restart
platform-infra/prod-debian/scripts/serverctl status
platform-infra/prod-debian/scripts/serverctl backup
```

## Re-run vs Reset

Short answer: most setup/deploy scripts are idempotent. For normal updates, rerun install/deploy scripts. Use reset only when you need to clean previous state.

Safe to rerun directly:

- `setup-host.sh`
- `setup-postgres.sh`
- `install-systemd.sh`
- `install-nginx.sh`
- `deploy-all.sh`

Use cleanup/reset scripts when you explicitly want a clean slate.

### Non-destructive cleanup (recommended routine)

Release pruning is no longer needed in the direct-source deployment model:

```bash
platform-infra/prod-debian/scripts/cleanup-releases.sh
```

The script now just reports that there are no release folders to prune.

### Reset mode: keep data (default)

This mode removes venvs, but keeps:

- `/runtime/shared/*` app runtime data
- `/etc/nightcraft/*.env`
- postgres data

```bash
sudo platform-infra/prod-debian/scripts/serverctl reset
```

### Reset mode: remove app shared data

This mode also deletes `/runtime/shared/*` runtime data:

```bash
sudo platform-infra/prod-debian/scripts/serverctl reset --remove-shared-data
```

### Reset mode: full wipe (infra + config + DB)

This is the most destructive mode. It also removes env files, systemd units, nginx site config, and postgres DB/roles:

```bash
sudo platform-infra/prod-debian/scripts/serverctl reset --remove-shared-data --with-env --with-systemd --with-nginx --with-postgres
```

### Backup all user data before destructive operations

Backup everything relevant in one command:

```bash
sudo platform-infra/prod-debian/scripts/serverctl backup
```

This includes:

- postgres logical dumps
- `/etc/nightcraft` env files
- `/runtime/shared/*` app runtime data

### Fresh install scenario

Use this when provisioning a new server or after a full wipe:

```bash
chmod +x platform-infra/prod-debian/scripts/*.sh
chmod +x platform-infra/prod-debian/scripts/serverctl
sudo platform-infra/prod-debian/scripts/setup-host.sh
sudo platform-infra/prod-debian/scripts/install-env.sh
sudo platform-infra/prod-debian/scripts/setup-postgres.sh
sudo platform-infra/prod-debian/scripts/install-systemd.sh
sudo platform-infra/prod-debian/scripts/install-nginx.sh
platform-infra/prod-debian/scripts/serverctl deploy
platform-infra/prod-debian/scripts/serverctl status
```

Then bootstrap again:

```bash
sudo platform-infra/prod-debian/scripts/setup-host.sh
sudo platform-infra/prod-debian/scripts/setup-postgres.sh
sudo platform-infra/prod-debian/scripts/install-systemd.sh
sudo platform-infra/prod-debian/scripts/install-nginx.sh
platform-infra/prod-debian/scripts/serverctl deploy
```

If you need to refresh env values from repo defaults:

```bash
sudo platform-infra/prod-debian/scripts/install-env.sh --overwrite
```

## Maintenance

Daily/regular operations:

- `platform-infra/prod-debian/scripts/serverctl status`
- `platform-infra/prod-debian/scripts/serverctl restart`
- `platform-infra/prod-debian/scripts/cleanup-releases.sh 5`

Weekly backups:

- `sudo platform-infra/prod-debian/scripts/serverctl backup`

Deployment history:

- `platform-infra/prod-debian/scripts/status-deploys.sh`
- `/runtime/deploy-history.csv`

Before risky change windows:

- run `serverctl backup`
- apply update/reset
- run `serverctl deploy`
- verify via `serverctl status` and smoke URLs

If you clone/copy fresh files, ensure scripts are executable:

```bash
chmod +x platform-infra/prod-debian/scripts/*.sh
```

## Troubleshooting

If `setup-postgres.sh` fails with `SQL template preflight failed`:

1. Read the line-number hints printed by the script.
1. Fix or re-sync `platform-infra/prod-debian/postgres/users-and-permissions.sql` and `platform-infra/prod-debian/postgres/create-dbs.sql`.
1. Re-run:

```bash
sudo platform-infra/prod-debian/scripts/setup-postgres.sh
```

If `setup-postgres.sh` fails with `invalid command \` from `users-and-permissions.sql`:

1. Update/sync repo files on the VPS with the latest `platform-infra/prod-debian/postgres/users-and-permissions.sql`.
2. Re-run:

```bash
sudo platform-infra/prod-debian/scripts/setup-postgres.sh
```

If role/database creation failed part-way, rerunning `setup-postgres.sh` is safe.

## Notes About Deployment Options

This structure supports your staged delivery model:

- Option 1 (single app standalone): Linux script path can reuse this release/systemd/nginx layout with app-only env and no auth dependency.
- Option 2 (auth + single app): implemented here for `service-auth + app-radio`.
- Option 3 (full server stack): this folder is the base pattern to extend with additional app units/env/scripts.

When you are ready, upload `app-landing`, `app-admin`, `app-radio`, `app-artsy`, `service-auth`, and `platform-infra/prod-debian` to the server and run the steps above.
