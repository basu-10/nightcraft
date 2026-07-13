# Concise overview of how the **Nightcraft** production server is wired up on the Debian 12 server:

---

login to production server with(most permissionsenabled):
ssh ionos-dev

## Server Architecture — Nightcraft Stack

### 1. OS & User

- **Debian 12** fresh install.
- A single unprivileged user `dev:dev` runs all app processes.

### 2. Directory Layout on Server

ALL source code git-checkouted under /nightcraft-source-code/ (set via --target-dir).
production server scripts, configs, and systemd units under /nightcraft-source-code/platform-infra/prod-debian/
runtime venvs and mutable app data under /runtime/

App source folders like:
"/nightcraft-source-code/app-admin/"
"/nightcraft-source-code/app-artsy/"
"/nightcraft-source-code/app-game/"
"/nightcraft-source-code/app-landing/"

Runtime folders like:
"/runtime/shared/app-admin/"
"/runtime/shared/app-artsy/"
"/runtime/shared/app-game/"
"/runtime/shared/app-landing/"

### 3. The 8 Apps

| App           | Port | Slug               | DB                          | systemd unit                | WSGI entry         |
| ------------- | ---- | ------------------ | --------------------------- | --------------------------- | ------------------ |
| **auth**      | 5100 | service-auth       | `auth_db`                   | nightcraft-auth.service     | `run:app`          |
| **radio**     | 5333 | `dev-podcast-app`  | `radio_db`                  | nightcraft-radio.service    | `run:app`          |
| **landing**   | 5400 | app-landing        | none                        | nightcraft-landing.service  | `wsgi:application` |
| **admin**     | 5500 | app-admin          | none                        | nightcraft-admin.service    | `wsgi:application` |
| **NEERA**     | 5600 | app-artsy          | PostgreSQL (`DATABASE_URL`) | nightcraft-neera.service    | `run:app`          |
| **seeksage**  | 5700 | `seeksage-backend` | PostgreSQL (`DATABASE_URL`) | nightcraft-seeksage.service | `run:app`          |
| **game**      | 5800 | app-game           | none                        | nightcraft-game.service     | `wsgi:app`         |
| **notestack** | 5900 | app-note           | none                        | nightcraft-note.service     | `wsgi:application` |

- Landing & Game are standalone (no `After=` dependency on auth/PostgreSQL).
- Auth, Radio, NEERA, Admin, SeekSage, and NoteStack declare `After=postgresql.service` and/or `After=nightcraft-auth.service` as needed.
- All use **Gunicorn** with 2–3 workers, bound to `127.0.0.1:<port>`.

### 4. PostgreSQL

- Two roles: `auth_app` / `radio_app` (each with a login password).
- Two databases: `auth_db` (owned by `auth_app`) / `radio_db` (owned by `radio_app`).
- Auth and radio are primary PostgreSQL-backed services.
- NEERA and SeekSage are now PostgreSQL-backed via `DATABASE_URL`.
- Landing, admin, and game do not require PostgreSQL.
- NoteStack is the remaining legacy exception with app-local SQLite internals (PostgreSQL migration is in progress).
- Connectivity: `127.0.0.1:5432` via psycopg v3 (`postgresql+psycopg://`).
- `setup-postgres.sh` preflights SQL templates for required `\set ON_ERROR_STOP on`, orphan backslash lines, and malformed `\ gexec` spacing before invoking psql.
- If explicit DB role variables are omitted, `setup-postgres.sh` derives NEERA/SeekSage/NoteStack role names, passwords, and database names from the corresponding env files.

### 5. Nginx Reverse Proxy

- Single nightcraft.conf at `/etc/nginx/sites-available/`, symlinked to `sites-enabled/`.
- Default Debian site is removed.
- Routes URL paths to upstreams:
  - `/` → landing (5400)
  - `/auth/` → auth (5100)
  - `/admin/` → admin (5500)
  - `/devradio/` → radio (5333)
  - `/neera/` → NEERA (5600)
  - `/seeksage/` → seeksage (5700)
  - `/game/` → game (5800)
  - `/notestack/` → notestack (5900)
- Trailing-slash redirects exist for each path root.
- Game uses lightweight client polling (no SSE); nginx `/game/` keeps `client_max_body_size 64m` for EmulatorJS ROM uploads.
- Catch-all server block returns `444` for unknown hostnames.
- Exposes public IP `31.70.85.89` on port 80.

### 6. Deployment Flow

1. Preferred: run one bootstrap script from outside `/nightcraft-source-code` (for example `/usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh`) so git sync + install + deploy are fully scripted from one command.

   Example (matches what GitHub Actions runs):
   - `sudo /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh --repo-url https://github.com/basu-10/nightcraft.git --branch main --target-dir /nightcraft-source-code --adopt-existing --force-sync`

The script performs baseline checks, clones/pulls git repo into `/nightcraft-source-code/`, runs setup scripts, deploys all apps, resyncs Neera PostgreSQL provisioning from `/etc/nightcraft/app-neera.env` during deploy, restarts services, and prints status.
The final status command used by `deploy-all.sh` and `status-all.sh` is intentionally non-fatal (`systemctl status ... || true`), so one stopped service does not suppress the status output for the rest of the stack.

2. Legacy/manual flow: `scp -r` local source folders to `/nightcraft-source-code/` on the server (some folders are large, so copy only changed files or zip/unzip if needed).
3. Run scripts (as root) in order:
   - `install-env.sh` — copies `.env` files from `platform-infra/prod-debian/env-examples/` to `/etc/nightcraft/`; required services fail without a template, optional services keep existing env files or skip when no template exists, and `--overwrite`/`OVERWRITE=1` forces replacement
   - `setup-postgres.sh` — creates DB roles & databases from SQL templates
   - `install-systemd.sh` — copies `.service` files to `/etc/systemd/system/` and enables them
   - `install-nginx.sh` — copies nginx config, tests, reloads
   - `deploy-all.sh` — runs per-app deploy scripts sequentially, then restarts all services
4. Each deploy script (deploy-auth.sh, etc.) does:
   - Uses the source checkout already present under `/nightcraft-source-code/<app>/`
   - Sets up virtualenv under `/runtime/venvs/<slug>/` + `pip install -r requirements.txt`
   - Ensures runtime shared dirs exist under `/runtime/shared/<slug>/`
   - Chowns runtime shared & venv dirs to `dev:dev`
   - `deploy-seeksage.sh` builds the React Workspace SPA with `VITE_BASE_PATH=/seeksage/` when npm is available, otherwise Flask UI falls back to the dashboard
   - `deploy-note.sh` requires `NOTESTACK_DB_BACKEND=postgres`; if `DATABASE_URL` is absent it derives the default NoteStack PostgreSQL URL and writes it to `/etc/nightcraft/app-note.env`; sync logs are kept under `/runtime/shared/app-note/localappdata/ABasu_apps/NoteStack/sync.log`
   - `deploy-neera.sh` resyncs PostgreSQL provisioning from `/etc/nightcraft/app-neera.env` before running NEERA setup

### 7. Key OAuth/SSO Details

- Auth service acts as **OIDC provider** at `http://31.70.85.89/auth`.
- deploy-all.sh seeds OAuth clients (auth, NEERA, seeksage, game) and user accounts after code deployment.
- NoteStack uses shared session bridging against `/auth/session/me`, so it does not require a separate OAuth client seed step.
- Post-login `next` URLs are preserved for cross-app destinations. Absolute/open redirects are rejected, and `X-Forwarded-Prefix` is applied only to auth-internal paths such as `/oauth/`, `/login`, `/register`, `/logout`, `/session/`, and `/healthz`.

### 8. GitHub Actions Setup

- `.github/workflows/deploy.yml`:

> **Note:** The bootstrap script at `/usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh` is **not** in the GitHub repo — it's kept separately on the server.
> Copy it with a dedicated SCP command per file (one SCP per file), not a multi-file glob. SCP flattens multiple source paths to the destination directory, so `scp file1 file2 dir/` works but `scp ../file1 sub/file2 dir/` loses relative paths.
> Deploy happens by simply pushing to `main`. GitHub Actions picks it up via `deploy.yml` and runs the SSH command on the server.
>
> Deploy logs are in `/var/log/nightcraft-deploy/`. A summary (success/failure) is written to `/runtime/deploy-history.csv`.
>
> **Important:** The `--target-dir /nightcraft-source-code` means the git repo is cloned to `/nightcraft-source-code/`. Nothing else should live in that folder — it is the source-checkout only. Runtime data lives under `/runtime/`, persistent env files under `/etc/nightcraft/`.

```yaml
name: Deploy Nightcraft

on:
  push:
    branches:
      - main

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Run deployment script on IONOS VPS
        uses: appleboy/ssh-action@v1.2.5
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            sudo /usr/local/sbin/server-scripts/nightcraft-server-bootstrap.sh \
              --repo-url https://github.com/basu-10/nightcraft.git \
              --branch main \
              --target-dir /nightcraft-source-code \
              --adopt-existing \
              --force-sync
```

---
