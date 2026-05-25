

Here's a concise overview of how the **Nightcraft** production server is wired up on the Debian 12 server:

---
login with:
ssh ionos-dev

## Server Architecture — Nightcraft Stack

### 1. OS & User
- **Debian 12** fresh install.
- A single unprivileged user `dev:dev` runs all app processes.

### 2. Directory Layout on Server

ALL source code under /platform-infra/
production server code and configs under /platform-infra/prod-debian/
runtime venvs and mutable app data under /platform-infra/runtime/

App folders like:
"/platform-infra/app-admin/"
"/platform-infra/app-artsy/"
"/platform-infra/app-game/"
"/platform-infra/app-landing/"

Runtime folders like:
"/platform-infra/runtime/shared/app-admin/"
"/platform-infra/runtime/shared/app-artsy/"
"/platform-infra/runtime/shared/app-game/"
"/platform-infra/runtime/shared/app-landing/"

### 3. The 8 Apps

| App | Port | Slug | DB | systemd unit | WSGI entry |
|---|---|---|---|---|---|
| **auth** | 5100 | service-auth | `auth_db` | nightcraft-auth.service | `run:app` |
| **radio** | 5333 | `dev-podcast-app` | `radio_db` | nightcraft-radio.service | `run:app` |
| **landing** | 5400 | app-landing | none | nightcraft-landing.service | `wsgi:application` |
| **admin** | 5500 | app-admin | none | nightcraft-admin.service | `wsgi:application` |
| **curio** | 5600 | app-artsy | PostgreSQL (`DATABASE_URL`) | nightcraft-curio.service | `run:app` |
| **seeksage** | 5700 | `seeksage-backend` | PostgreSQL (`DATABASE_URL`) | nightcraft-seeksage.service | `run:app` |
| **game** | 5800 | app-game | none | nightcraft-game.service | `wsgi:app` |
| **notestack** | 5900 | app-note | none | nightcraft-note.service | `wsgi:application` |

- Landing & Game are standalone (no `After=` dependency on auth/PostgreSQL).
- Auth, Radio, Curio, Admin, SeekSage, and NoteStack declare `After=postgresql.service` and/or `After=nightcraft-auth.service` as needed.
- All use **Gunicorn** with 2–3 workers, bound to `127.0.0.1:<port>`.

### 4. PostgreSQL
- Two roles: `auth_app` / `radio_app` (each with a login password).
- Two databases: `auth_db` (owned by `auth_app`) / `radio_db` (owned by `radio_app`).
- Auth and radio are primary PostgreSQL-backed services.
- Curio and SeekSage are now PostgreSQL-backed via `DATABASE_URL`.
- Landing, admin, and game do not require PostgreSQL.
- NoteStack is the remaining legacy exception with app-local SQLite internals.
- Connectivity: `127.0.0.1:5432` via psycopg2.

### 5. Nginx Reverse Proxy
- Single nightcraft.conf at `/etc/nginx/sites-available/`, symlinked to `sites-enabled/`.
- Default Debian site is removed.
- Routes URL paths to upstreams:
  - `/` → landing (5400)
  - `/auth/` → auth (5100)
  - `/admin/` → admin (5500)
  - `/devradio/` → radio (5333)
  - `/curio/` → curio (5600)
  - `/seeksage/` → seeksage (5700)
  - `/game/` → game (5800)
   - `/notestack/` → notestack (5900)
- Trailing-slash redirects exist for each path root.
- Game gets `proxy_buffering off` + 600s read timeout (for SSE).
- Catch-all server block returns `444` for unknown hostnames.
- Exposes public IP `31.70.85.89` on port 80.

### 6. Deployment Flow
1. `scp -r` local source folders to platform-infra on the server.(some fodler are large, so copy only changed files or zip/unzip if needed)
2. Run scripts (as root) in order:
   - install-env.sh — copies `.env` files from `env-examples/` to `/etc/nightcraft/`
   - setup-postgres.sh — creates DB roles & databases from SQL templates
   - install-systemd.sh — copies `.service` files to `/etc/systemd/system/` and enables them
   - install-nginx.sh — copies nginx config, tests, reloads
   - deploy-all.sh — runs per-app deploy scripts sequentially, then restarts all services
3. Each deploy script (deploy-auth.sh, etc.) does:
   - Uses the source checkout already present under `/platform-infra/<app>/`
   - Sets up virtualenv + `pip install -r requirements.txt`
   - Ensures runtime shared dirs exist under `/platform-infra/runtime/shared/<slug>/`
   - Chowns runtime shared & venv dirs to `dev:dev`

### 7. Key OAuth/SSO Details
- Auth service acts as **OIDC provider** at `http://31.70.85.89/auth`.
- deploy-all.sh seeds OAuth clients (auth, curio, seeksage, game) and user accounts after code deployment.
- NoteStack uses shared session bridging against `/auth/session/me`, so it does not require a separate OAuth client seed step.

---
