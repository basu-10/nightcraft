# Prod Debian Infrastructure

This folder is the production Linux deployment hub for Nightcraft apps.

Current target in this phase:

- `app-landing` (root product hub)
- `service-auth` (OIDC/SSO provider)
- `app-radio` (DevRadio client app, `AUTH_MODE=sso`, routed under `/devradio`)
- `app-artsy` (Curio client app, `AUTH_MODE=sso`, routed under `/curio`)
- `app-researchAgent/seeksage/backend` (SeekSage app API, `AUTH_MODE=sso`, routed under `/seeksage`)
- `app-note` (NoteStack app, shared-session auth via `service-auth`, routed under `/notestack`)
- `app-admin` (admin login handoff app)

Production routing on the server is path-based on the single host `31.70.85.89`:

- `http://31.70.85.89/` -> app-landing
- `http://31.70.85.89/auth` -> service-auth
- `http://31.70.85.89/devradio` -> app-radio
- `http://31.70.85.89/curio` -> app-artsy (Curio)
- `http://31.70.85.89/seeksage` -> app-researchAgent/seeksage/backend (SeekSage)
- `http://31.70.85.89/notestack` -> app-note (NoteStack)
- `http://31.70.85.89/admin` -> app-admin

All setup, deploy, seed, start, stop, and backup operations are script-driven from `platform-infra/prod-debian/scripts`.

Primary operations can be run through the single dispatcher command `serverctl` in that folder.

Deployment runs are logged on the VPS under `/var/log/nightcraft-deploy/`, and each bootstrap run appends a CSV summary to `/platform-infra/deploy-history.csv`.

## Single-Command Server Bootstrap

Use `server-scripts/nightcraft-server-bootstrap.sh` to run the whole flow from one command:

- validates baseline server requirements
- clones or updates repo from git
- runs env/postgres/systemd/nginx install scripts
- runs app deploy and service restart via `deploy-all.sh`

Each run creates a timestamped log in `/var/log/nightcraft-deploy/` and appends a deployment record to `/platform-infra/deploy-history.csv` with start time, commit, duration, and success/failure.

Recommended on the VPS: keep this script outside the checkout (for example under `/usr/local/sbin/server-scripts`) and point it at `/platform-infra`.

Example install and run:

```bash
sudo install -d -m 0755 /usr/local/sbin/server-scripts
sudo install -m 0755 /tmp/nightcraft-server-bootstrap.sh /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh
sudo /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh \
  --repo-url https://github.com/basu-10/nightcraft.git \
  --branch main \
  --target-dir /platform-infra \
  --adopt-existing
```

Useful flags:

- `--check-only` preflight only
- `--force-sync` force checkout to `origin/<branch>`
- `--overwrite-env` overwrite `/etc/nightcraft/*.env` from repo templates
- `--skip-postgres`, `--skip-nginx`, `--skip-systemd`, `--skip-deploy` for partial runs
- `--run-host-setup` or `--skip-host-setup` for setup-host control

To inspect deployment history after runs:

```bash
platform-infra/prod-debian/scripts/status-deploys.sh
```

## Folder Layout

- `nginx/nightcraft.conf`: reverse proxy config for landing/auth/devradio/curio/seeksage/notestack/admin
- `systemd/nightcraft-auth.service`: Gunicorn service for auth
- `systemd/nightcraft-radio.service`: Gunicorn service for radio
- `systemd/nightcraft-curio.service`: Gunicorn service for Curio
- `systemd/nightcraft-seeksage.service`: Gunicorn service for SeekSage
- `systemd/nightcraft-landing.service`: Gunicorn service for landing
- `systemd/nightcraft-admin.service`: Gunicorn service for admin handoff
- `systemd/nightcraft-note.service`: Gunicorn service for NoteStack
- `postgres/users-and-permissions.sql`: role/user creation SQL
- `postgres/create-dbs.sql`: DB creation/grant SQL
- `env-examples/service-auth.env`: exact file for `/etc/nightcraft/service-auth.env`
- `env-examples/app-radio.env`: exact file for `/etc/nightcraft/app-radio.env`
- `env-examples/app-curio.env`: exact file for `/etc/nightcraft/app-curio.env`
- `env-examples/app-seeksage.env`: exact file for `/etc/nightcraft/app-seeksage.env`
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
- `scripts/deploy-curio.sh`: release deploy for app-artsy
- `scripts/deploy-seeksage.sh`: release deploy for seeksage backend
  - Flask UI is server-rendered; no Node/npm frontend build step is required.
- `scripts/deploy-landing.sh`: release deploy for app-landing
- `scripts/deploy-admin.sh`: release deploy for app-admin
- `scripts/deploy-note.sh`: release deploy for app-note
- `scripts/seed-auth-users.sh`: seed one service-auth user and one admin user
- `scripts/seed-auth-client.sh`: seed OAuth client/user for radio callback
- `scripts/seed-curio-client.sh`: seed OAuth client/user for Curio callback
- `scripts/seed-seeksage-client.sh`: seed OAuth client/user for SeekSage callback
- `scripts/deploy-all.sh`: landing + auth + radio + curio + seeksage + admin + notestack deploy + seed + restart
- `scripts/start-all.sh`: start landing + auth + radio + curio + seeksage + admin + notestack
- `scripts/stop-all.sh`: stop landing + auth + radio + curio + seeksage + admin + notestack
- `scripts/restart-all.sh`: restart landing + auth + radio + curio + seeksage + admin + notestack + reload nginx
- `scripts/status-all.sh`: service status overview
- `scripts/backup-postgres.sh`: logical postgres backups
- `scripts/backup-all.sh`: backup postgres + `/etc/nightcraft` + `/platform-infra/runtime/shared/*`
- `scripts/cleanup-releases.sh`: obsolete helper kept only to report that release pruning is no longer needed
- `scripts/reset-stack.sh`: reset app deploy state with keep-data default and explicit remove-data mode
- `scripts/serverctl`: single command dispatcher for deploy/backup/status/restart/start/stop/reset
- `scripts/status-deploys.sh`: summarize `/platform-infra/deploy-history.csv` into a readable deployment report

## Runtime Layout Used On Server

Apps run directly from the source checkout under `/platform-infra`:

- `/platform-infra/app-landing`
- `/platform-infra/service-auth`
- `/platform-infra/app-radio`
- `/platform-infra/app-artsy`
- `/platform-infra/app-researchAgent/seeksage`
- `/platform-infra/app-admin`
- `/platform-infra/app-game`
- `/platform-infra/app-note`

Each app uses:

- Dedicated virtualenv under `/platform-infra/runtime/venvs/`
  - `/platform-infra/runtime/venvs/app-landing`
  - `/platform-infra/runtime/venvs/service-auth`
  - `/platform-infra/runtime/venvs/dev-podcast-app`
  - `/platform-infra/runtime/venvs/app-artsy`
  - `/platform-infra/runtime/venvs/seeksage-backend`
  - `/platform-infra/runtime/venvs/app-admin`
  - `/platform-infra/runtime/venvs/app-note`
- Runtime state under `/platform-infra/runtime/shared/`
  - `/platform-infra/runtime/shared/service-auth`
  - `/platform-infra/runtime/shared/dev-podcast-app`
  - `/platform-infra/runtime/shared/app-artsy`
  - `/platform-infra/runtime/shared/seeksage-backend`
  - `/platform-infra/runtime/shared/app-note`

## Expected Server Baseline

Validated against the provided host:

- Debian 13
- PostgreSQL active
- nginx active with default site
- existing runtime roots under `/platform-infra/runtime`

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
- `/etc/nightcraft/app-curio.env`
- `/etc/nightcraft/app-seeksage.env`
- `/etc/nightcraft/app-landing.env`
- `/etc/nightcraft/app-admin.env`
- `/etc/nightcraft/app-note.env`

Review and edit once if needed:

```bash
sudo nano /etc/nightcraft/app-landing.env
sudo nano /etc/nightcraft/service-auth.env
sudo nano /etc/nightcraft/app-radio.env
sudo nano /etc/nightcraft/app-curio.env
sudo nano /etc/nightcraft/app-seeksage.env
sudo nano /etc/nightcraft/app-admin.env
sudo nano /etc/nightcraft/app-note.env
```

1. Create DB users and databases.

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

## Server Control Entrypoint.....

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
- `OIDC_KEYS_DIR=/platform-infra/runtime/shared/service-auth/keys`

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
- `LANDING_ADMIN_URL=/admin`
- `LANDING_DEVRADIO_URL=/devradio`
- `LANDING_CURIO_URL=/curio`
- `LANDING_SEEKSAGE_URL=/seeksage`
- `LANDING_NOTESTACK_URL=/notestack`

In `/etc/nightcraft/app-curio.env`:

- `FLASK_ENV=production`
- `FLASK_SECRET_KEY`
- `FLASK_AUTH_MODE=sso`
- `FLASK_AUTH_SERVICE_URL=http://31.70.85.89/auth`
- `FLASK_AUTHLIB_CLIENT_ID=curio-app`
- `FLASK_AUTHLIB_CLIENT_SECRET`

In `/etc/nightcraft/app-seeksage.env`:

- `FLASK_ENV=production`
- `SECRET_KEY`
- `AUTH_MODE=sso`
- `AUTH_SERVICE_URL=http://31.70.85.89/auth`
- `AUTHLIB_CLIENT_ID=seeksage-app`
- `AUTHLIB_CLIENT_SECRET`

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
- `NOTESTACK_DB=/platform-infra/runtime/shared/app-note/notestack.db`
- `LOCALAPPDATA=/platform-infra/runtime/shared/app-note/localappdata`

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

- `/platform-infra/runtime/shared/*` app runtime data
- `/etc/nightcraft/*.env`
- postgres data

```bash
sudo platform-infra/prod-debian/scripts/serverctl reset
```

### Reset mode: remove app shared data

This mode also deletes `/platform-infra/runtime/shared/*` runtime data:

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
- `/platform-infra/runtime/shared/*` app runtime data

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
- `/platform-infra/deploy-history.csv`

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

When you are ready, upload `app-landing`, `app-admin`, `app-radio`, `app-artsy`, `app-researchAgent`, `service-auth`, and `platform-infra/prod-debian` to the server and run the steps above.
