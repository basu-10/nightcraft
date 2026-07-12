# The Green Pledge (`app-pledge`)

A Nightcraft product. This is the initial scaffold: a Flask backend with a
placeholder landing page, plus the startup/provisioning wiring that matches the
other Nightcraft apps (DevRadio / app-radio, NoteStack / app-note).

> Status: backend-first. The product experience is built on top of this
> foundation next. The public landing page is a placeholder for now.

## Layout

```
app-pledge/
  greenpledge/            # Flask application package
    __init__.py           # create_app factory (PostgreSQL-only, ProxyFix, auth mode)
    extensions.py         # db + login_manager
    models.py             # LocalCredential, UserProfile, Pledge
    guards.py             # auth_required / admin_required
    utils.py              # timezone helpers
    auth/                 # auth adapter layer (local_auth, sso_auth, current_user)
    landing.py            # placeholder landing/about routes
    cli.py                # `flask --app greenpledge setup`
    templates/            # base + landing + auth templates
    static/css/main.css
  run.py                  # gunicorn/flask entrypoint (port 5300)
  dev-start.ps1           # Windows dev bootstrap (venv + setup + run)
  requirements.txt
  pytest.ini
  tests/
```

## Architecture notes

- **Auth adapter layer** (`greenpledge/auth/`): the product code never talks to
  the users table directly. It calls `get_current_user()` from
  `greenpledge.auth.current_user`. Configuration decides behaviour:
  - `AUTH_MODE=local` &mdash; standalone, username/password in `local_credential`.
  - `AUTH_MODE=sso` &mdash; OAuth/OIDC client of `service-auth` (the central
    Nightcraft auth service). The app stores only `user_id` + product data.
- **PostgreSQL only**: `create_app` enforces a PostgreSQL DSN via
  `FLASK_SQLALCHEMY_DATABASE_URI`. SQLite is not supported, matching the rest
  of the stack.
- **Routing prefix**: served under `/pledge` behind nginx on the production
  server (see `platform-infra/prod-debian`).

## Local development

```powershell
# Windows
./dev-start.ps1            # local auth, uses the dev PostgreSQL DSN

# Or manually
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
$env:FLASK_SQLALCHEMY_DATABASE_URI = "postgresql+psycopg://green_pledge_app:...@127.0.0.1:5432/green_pledge_db"
flask --app greenpledge setup
flask --app greenpledge run --port 5300
```

## Production provisioning

The app is wired into the Nightcraft deployment the same way as the other apps:

- `platform-infra/prod-debian/scripts/deploy-pledge.sh` &mdash; venv + deps +
  `flask --app greenpledge setup`.
- `platform-infra/prod-debian/scripts/seed-pledge-client.sh` &mdash; registers
  the `green-pledge-app` OAuth client in `service-auth`.
- `platform-infra/prod-debian/env-examples/pledge.env.example` &rarr;
  `/etc/nightcraft/app-pledge.env`.
- `platform-infra/prod-debian/systemd/nightcraft-pledge.service` (port 5300).
- nginx `/pledge` route in `platform-infra/prod-debian/nginx/nightcraft.conf`.
- PostgreSQL role/db in `platform-infra/prod-debian/postgres/*.sql`.

Pushing to `main` triggers `.github/workflows/deploy.yml`, which runs the
server bootstrap (`nightcraft-server-bootstrap.sh`) that orchestrates the full
patch going live.

## Default accounts (local mode)

Seeded by `flask --app greenpledge setup`:

- `admin` / `admin123` (admin)
- `testuser` / `test123` (member)
