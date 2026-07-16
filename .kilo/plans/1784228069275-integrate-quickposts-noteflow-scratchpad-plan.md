# Plan: Integrate QuickPosts, NoteFlow & ScratchPad into the NightCraft ecosystem

## Goal
Promote the three experimental apps (currently self-contained HTML rendered by `app-landing`) into first-class, modularly-scaffolded Flask apps that live in their own folders, run as **on_demand** (runtime-mode) services behind Nginx, authenticate through the central OIDC provider (each with its own OAuth client + shared-session bridge), and persist **user-scoped** content in **per-app PostgreSQL** databases — mirroring the existing Alfred/Neera (on_demand + Postgres + SSO) pattern.

After the change, the `app-landing` experimental page keeps lightweight **landing/product pages** that gate on auth and then redirect into the running app subpath.

## Decisions (confirmed with user)
- **Storage:** PostgreSQL per-app (own DB + role, like Alfred/Neera).
- **Auth:** Full SSO OAuth client per app (`/auth/login` + `/auth/callback`), seeded via a `seed-<app>-client.sh`, plus the shared-session bridge (`/auth/session/me`) so the landing handoff login just works.
- **Slugs / public paths:** `quickposts` → `/quickposts`, `noteflow` → `/noteflow`, `scratchpad` → `/scratchpad`. Renames "QuickPost" → "QuickPosts" everywhere.
- **Landing pages + auth gating:** `app-landing` keeps a thin landing/marketing page per app that, on "Open app", builds an auth handoff (`/auth/login?next=/<slug>`) → app subpath.
- **Backward compat:** **Hard cutover** — old routes `/quickpost`, `/miobook`, `/scrapbook` are removed and return 404 (no 301 redirects). Existing bookmarks/links break by design.
- **CDN assets:** Migrated HTML keeps its existing external CDN tags (Tailwind CDN, Google Fonts, font-awesome, lucide) as-is — the apps require outbound internet, matching current behavior. No local vendoring.
- **Idle timeout:** **15m** for all three (matches Green Pledge).

## Products registry additions (`platform-infra/prod-debian/products.yml`)
Add three on_demand entries (reuse the existing schema; no code change needed in `products.py`/`runtime-manager`/`install-systemd`/`gen-nginx-on-demand` — they already iterate `nc_slugs`):

```yaml
  quickposts:
    display_name: QuickPosts
    slug: quickposts
    public_paths: [/quickposts]
    runtime:
      policy: on_demand
      service: nightcraft-quickposts.service
      port: 5310
      upstream: app_quickposts_upstream
      workers: 2
      idle_timeout: 15m
  noteflow:
    display_name: NoteFlow
    slug: noteflow
    public_paths: [/noteflow]
    runtime:
      policy: on_demand
      service: nightcraft-noteflow.service
      port: 5320
      upstream: app_noteflow_upstream
      workers: 2
      idle_timeout: 15m
  scratchpad:
    display_name: ScratchPad
    slug: scratchpad
    public_paths: [/scratchpad]
    runtime:
      policy: on_demand
      service: nightcraft-scratchpad.service
      port: 5330
      upstream: app_scratchpad_upstream
      workers: 2
      idle_timeout: 15m
```
Ports chosen in the 5310–5330 range (free per the existing registry which tops out at 5900 with 5300/5333 used by pledge/radio). Idle 15m matches Green Pledge.

## New app folders (one per product, identical structure — reuse Alfred as the template)
Create each under the repo root: `app-quickposts/`, `app-noteflow/`, `app-scratchpad/`. Each contains:

```
<app>/                       # e.g. app-quickposts
  run.py                     # `from quickposts import create_app; app = create_app()`
  requirements.txt           # flask, flask-login, flask-sqlalchemy, authlib, gunicorn, psycopg[binary], PyYAML
  pytest.ini
  <pkg>/                    # e.g. quickposts/
    __init__.py             # create_app(): ProxyFix, config.from_prefixed_env(), enforce Postgres DSN,
                           #   db.init_app, register auth blueprint, register app blueprint,
                           #   before_request bridge_shared_sso_session() when AUTH_MODE==sso,
                           #   context_processor inject_app_user, db.create_all()
    extensions.py            # db = SQLAlchemy(); login_manager
    config.py               # default config mapping (SECRET_KEY, AUTH_MODE, DATABASE_URL, AUTH_SERVICE_URL,
                           #   AUTHLIB_CLIENT_ID/SECRET, AUTH_LOGIN_PATH, RUNTIME_MANAGER_URL, APP_SLUG, SESSION_COOKIE_NAME)
    models.py               # UserProfile (user_id PK, username, display_name, is_admin, is_public) +
                           #   the app's content model keyed by user_id (see per-app schema below)
    auth/
      __init__.py          # get_auth_blueprint(app) -> blueprint at url_prefix="/<slug>/auth"
      sso_auth.py          # copy/adapt from app-alfred/alfred/auth/sso_auth.py (rename blueprint url_prefix + client id + session cookie name)
      current_user.py      # get_current_user() reading session["user_id"]
    routes.py              # bp = Blueprint("app", __name__, url_prefix="/<slug>")
                           #   GET /<slug>/            -> landing/product page (auth-gated, login CTA)
                           #   GET /<slug>/app         -> the actual app (requires login; 302 to /<slug>/auth/login?next=... otherwise)
                           #   GET /<slug>/healthz     -> {"status":"ok"}
                           #   /api/<entity> CRUD (user-scoped; see "Per-app content schema")
    templates/
      base.html            # shared shell (CSS vars, nav, logout form posting to /auth/logout)
      landing.html         # product/landing page
      app.html             # migrated app UI + a Save/Load control wired to /api/<entity> (see schema note)
    static/               # only if needed; CDN assets stay inline in app.html
    cli.py                # `flask --app <pkg> setup` -> db.create_all() ONLY (no local-user seed)
  tests/
    test_routes.py
```

`APP_SLUG` MUST equal the products.yml slug so the runtime-manager cold-start aligns. No backend keepalive module is needed (these are stateless content editors, unlike Alfred's long agent runs).

### Per-app content schema (`models.py`) — Core entity save/load
**Scope (confirmed):** the migrated HTML apps currently have **no persistence** (no `localStorage`/backend; they only export PNGs client-side). This integration adds a backend layer for the **primary entity** of each app, wired to save + auto-load on login. Other UI features stay client-side for now.

Content is **user-scoped**: every content row has `user_id` (String, indexed) and is always queried with the logged-in `session["user_id"]`. Minimal tables (one primary entity per app):

- **QuickPosts** (`quickposts/`): `QuickPost(id PK, user_id idx, title, body, layout, created_at, updated_at)` — the text draft the pipeline turns into posts/slides/edits (`quickposts-app-*.html` consume pasted text).
- **NoteFlow** (`noteflow/`): `Notebook(id PK, user_id idx, title, cells_json, created_at, updated_at)` — Jupyter-style prose + runnable blocks (`browser-notebook-app*.html`).
- **ScratchPad** (`scratchpad/`): `Pad(id PK, user_id idx, title, content_json, created_at, updated_at)` — spatial mindmap nodes/edges (`mindmap-*.html`).

**API contract (under the app blueprint, all require auth + filter by `session["user_id"]`):**
- `GET  /api/<entity>`      → list the user's items (or the single draft)
- `POST /api/<entity>`      → create; body `{title, body|cells_json|content_json, layout}`
- `GET  /api/<entity>/<id>` → fetch one (must belong to user)
- `PUT  /api/<entity>/<id>` → update
- `DELETE /api/<entity>/<id>` → delete
On `GET /<slug>/app`, the page JS auto-loads the user's existing item(s) via `GET /api/<entity>` and populates the editor; a "Save" control `POST`/`PUT`s back. Errors (401) trigger redirect to `/<slug>/auth/login?next=/<slug>/app`.

`cli.py setup` MUST only run `db.create_all()` (no local-user seed — these are SSO-only; do **not** import `LocalCredential` like Alfred's `cli.py`).

## Migrate the HTML (out of `app-landing`)
The current `app-landing/landing/templates/{quickposts-landing,quickposts-app-*,browser-notebook-*,mindmap-*}.html` are fully self-contained (own `<style>`, external CDN `<script>`/`<link>`, do NOT extend `landing/templates/base.html`, do NOT use `url_for('static',...)`, and contain **no** `localStorage`/`fetch`/root-relative `/` links). Verified safe to move and to serve under a subpath. For each app:
1. Move the **app UI** HTML into `<pkg>/templates/app.html` and the **landing** HTML into `<pkg>/templates/landing.html`. The HTML keeps working as-is (inline styles + absolute `https://` CDN URLs resolve under the subpath).
2. **Keep CDN links as-is** (Tailwind CDN, Google Fonts, font-awesome, lucide) — no local vendoring. The app UI needs outbound internet (matches current behavior).
3. **Add persistence wiring (new):** the migrated UI has no save logic. Add a minimal "Save" / auto-load control in `app.html` JS that calls the new `/api/<entity>` endpoints (contract above). On page load, `GET /api/<entity>` and populate the editor; on Save, `POST`/`PUT`. This is the only frontend change needed for the core-entity scope; other UI features remain client-side.
4. Wire the logout control to `POST /auth/logout?next=/<slug>` (unified logout).
5. **Delete** the migrated templates from `app-landing/landing/templates/` and remove the now-dead routes in `app-landing/landing/routes.py` (`/quickpost*`, `/miobook*`, `/scrapbook*`, and the QuickPost/NoteFlow/ScratchPad sections in `/experimental`). These old routes 404 after cutover.

## `app-landing` changes (auth-gated product pages + experimental page)
- `app-landing/config.py`: add `QUICKPOSTS_URL`, `NOTEFLOW_URL`, `SCRATCHPAD_URL` env-backed defaults (`/quickposts`, `/noteflow`, `/scratchpad`). Drop the legacy `QUICKPOST_URL` (no redirect shim — hard cutover).
- `app-landing/landing/routes.py`:
  - Add `GET /quickposts`, `GET /noteflow`, `GET /scratchpad` that render a **thin landing page** (the app's `landing.html` is served by the app itself; landing only shows a card + "Open app" button that builds `build_auth_handoff_url(AUTH_URL, "/<slug>", AUTH_RETURN_PARAM)` so the user logs in then lands in the app). Reuse the existing `_fetch_shared_auth_user` + `build_auth_handoff_url` helpers (already modular).
  - In `/experimental`, replace the QuickPost/NoteFlow/ScratchPad `url`s with `/quickposts`, `/noteflow`, `/scratchpad` and update the "status" from "In Development" to "Active".
- Update `app-landing/tests/test_routes.py` (remove assertions for deleted `/quickpost` etc., assert new `/quickposts`/`/noteflow`/`/scratchpad` render and experimental still lists the three).

## Deployment plumbing (replicate Alfred/Neera exactly — these are the reusable, modular pieces)
1. **`common.sh`** — add slug/dir/venv vars for the three apps (mirror `ALFRED_*` block):
   ```
   QUICKPOSTS_SLUG="${QUICKPOSTS_SLUG:-app-quickposts}"   QUICKPOSTS_SRC_DIR / _SHARED_DIR / _VENV_DIR
   NOTEFLOW_SLUG=...   SCRATCHPAD_SLUG=...
   ```
   No change needed to the `nc_*` helper functions — they read everything from products.yml.
2. **systemd units** (`platform-infra/prod-debian/systemd/`): create `nightcraft-quickposts.service`, `nightcraft-noteflow.service`, `nightcraft-scratchpad.service`, copied from `nightcraft-alfred.service` with: `Description`, `WorkingDirectory=/nightcraft-source-code/app-<x>`, `EnvironmentFile=/etc/nightcraft/app-<x>.env`, `ExecStart=/runtime/venvs/<slug>/bin/python -m gunicorn --workers 2 --bind 127.0.0.1:<port> run:app`. `install-systemd.sh` already installs + disables on_demand units automatically.
3. **nginx upstreams** (`nginx/nightcraft.conf`): add `app_quickposts_upstream` (127.0.0.1:**5310**), `app_noteflow_upstream` (**5320**), `app_scratchpad_upstream` (**5330**). The per-path proxy blocks + cold-start loader are generated by `gen-nginx-on-demand.sh` from `public_paths` — no manual location blocks needed.
4. **env examples** (`platform-infra/prod-debian/env-examples/`): add `quickposts.env.example`, `noteflow.env.example`, `scratchpad.env.example`, copied from `alfred.env.example` with:
   - `FLASK_AUTH_MODE=sso`, `FLASK_AUTH_SERVICE_URL=http://31.70.85.89/auth`
   - `FLASK_AUTHLIB_CLIENT_ID=<slug>-app` / `FLASK_AUTHLIB_CLIENT_SECRET=<slug>-app-client-secret-2026`
   - `DATABASE_URL=postgresql+psycopg://<slug>_app:change_me@127.0.0.1:5432/<slug>_db`
   - `FLASK_UPLOADS_DIR=/runtime/shared/app-<x>/instance/uploads`
   - `RUNTIME_MANAGER_URL=http://127.0.0.1:5700`, `APP_SLUG=<slug>`
   - distinct `FLASK_SECRET_KEY` and `SESSION_COOKIE_NAME` per app.
5. **deploy scripts** (`platform-infra/prod-debian/scripts/`): add `deploy-quickposts.sh`, `deploy-noteflow.sh`, `deploy-scratchpad.sh` — copy `deploy-alfred.sh`, swap `ALFRED_*` → app-specific vars, change the setup CLI to `<pkg>` (`FLASK_AUTH_MODE=sso <venv>/bin/python -m flask --app <pkg> setup`). Keep the `setup-postgres.sh` call (idempotent per-app DB provisioning).
6. **seed client scripts**: add `seed-quickposts-client.sh`, `seed-noteflow-client.sh`, `seed-scratchpad-client.sh` — copy `seed-alfred-client.sh`, set `AUTH_SEED_CLIENT_ID=<slug>-app`, `AUTH_SEED_CLIENT_SECRET=<slug>-app-client-secret-2026`, `PUBLIC_PATH=/<slug>`. (Reuses `devuser` account per the "OAuth client seed reused" convention.)
7. **`setup-postgres.sh`** — add the three apps to the role/db provisioning:
   - Add `QUICKPOSTS_*` / `NOTEFLOW_*` / `SCRATCHPAD_*` env defaults (`<slug>_db` / `<slug>_app` / `<slug>_app_db_2026_prod_secret`) and `_extract_database_url_from_env_file` blocks reading `/etc/nightcraft/app-<x>.env`.
   - Pass the new `-v <slug>_db_user/_db_password` vars into the `users-and-permissions.sql` and `create-dbs.sql` invocations.
    - **Also** add matching blocks to `platform-infra/prod-debian/postgres/users-and-permissions.sql` and `create-dbs.sql` (mirror the `alfred_*` entries exactly): `CREATE ROLE %I LOGIN PASSWORD %L WHERE NOT EXISTS ... \gexec` + `ALTER ROLE %I WITH LOGIN PASSWORD %L \gexec` in `users-and-permissions.sql`; `CREATE DATABASE %I OWNER %I ENCODING 'UTF8' WHERE NOT EXISTS ... \gexec` + `GRANT ALL PRIVILEGES ON DATABASE %I TO %I \gexec` in `create-dbs.sql`. Honor the `ON_ERROR_STOP on` + `\gexec` (no space) conventions validated by the script's preflight.
8. **`deploy-all.sh`** — add the three `deploy-<x>.sh` calls (after `deploy-alfred.sh`) and the three `seed-<x>-client.sh` calls (after `seed-alfred-client.sh`). The existing trailing steps (push manifest, regen nginx, restart manager, reload nginx) already cover the new on_demand apps.

## Single Sign-On across all NightCraft apps (REQUIRED)

**Goal (user requirement):** a user who logs in to one app must NOT have to log in again to use the others on the same server.

**Verified: the existing architecture already provides this** via a shared central session cookie + per-app bridge. No new auth service changes are needed. Mechanism (confirmed in code):

1. `service-auth` sets the session cookie `nightcraft_auth_session` with `SESSION_COOKIE_PATH = /` and **no explicit `Domain`**, on host `31.70.85.89` (`serviceauth/config.py:6-8`). Therefore the browser sends this cookie on **every** request to `31.70.85.89` regardless of subpath (`/auth`, `/alfred`, `/quickposts`, …).
2. `service-auth` exposes `GET /session/me` which reads that cookie and returns `{authenticated, user}` (`auth_routes.py:410-423`).
3. Each SSO app installs a `before_request` hook `ensure_session_from_shared_auth()` (`app-alfred/alfred/auth/sso_auth.py:145-157`) that, when its own `session["user_id"]` is absent, calls `/auth/session/me` forwarding the browser `Cookie` header, and on success establishes the **app-local** Flask session (`_sync_profile_and_session`).
4. Nginx `proxy_pass` forwards the `Cookie` header to app subpaths by default (the landing's `_fetch_shared_auth_user` already depends on this — proven in production).

**Consequence:** If a user is logged in via *any* app (e.g. Alfred or the landing handoff), then opens `/quickposts`, the new app's `before_request` bridge sees the shared `nightcraft_auth_session` cookie, silently re-establishes the local session, and the user is **already authenticated — zero redirects to login**. Only when the shared cookie is also absent does the app redirect to `/auth/login?next=/<slug>`.

**Hard requirements for each new app (non-negotiable for SSO):**
- Copy `app-alfred/alfred/auth/*` (with `url_prefix="/<slug>/auth"`, config-driven `AUTHLIB_CLIENT_ID`, distinct `SESSION_COOKIE_NAME` per app so app-local cookies never collide). Each app keeps its OWN OAuth client (the user chose "SSO OAuth client each") — this is complementary: the OAuth client completes first login; the shared cookie enables subsequent cross-app SSO without re-running OAuth.
- Register the global `before_request` bridge in `create_app()` **only when `AUTH_MODE==sso`** (mirror `alfred/__init__.py:88-93`). This is what makes cross-app SSO work.
- Guard app/content routes with `auth_required` (from `guards.py`) so unauthenticated users redirect to `/<slug>/auth/login?next=...` — but the bridge runs *before* that check, so already-logged-in users never hit it.

**Landing handoff behavior (UX):** The landing "Open app" button builds `build_auth_handoff_url(AUTH_URL, "/<slug>", AUTH_RETURN_PARAM)` → `/auth/login?next=/<slug>`.
- If the user is **not** logged in: they see the auth login page once, then land in the app.
- If the user **is** already logged in (via another app): the `/auth/login` GET currently re-renders the login page (`auth_routes.py:391` does not auto-redirect when authenticated). To avoid this redundant step, the landing CTA should first check `_fetch_shared_auth_user()`; when already authenticated, deep-link straight to `/<slug>/app` instead of the handoff. (Minor enhancement; the bridge still guarantees no re-login either way.)

**Unified logout (document, do not change):** `/auth/logout` clears the shared `nightcraft_auth_session` cookie, which logs the user out of **all** apps at once. This is the correct, expected SSO behavior. Each app's logout must POST to `/auth/logout?next=/<slug>` (the existing landing `logout_url` pattern), NOT clear only its app-local cookie.

**Validation of SSO specifically (add to Validation section):**
- Log in via `/auth/login` (or Alfred). Then, in the **same browser**, open `/quickposts/app` directly (cold-start the service first via a prior hit). Assert the app shows the authenticated UI with the correct `user_id` and **no** redirect to a login page.
- Log in as user A in one browser tab (app X), confirm a second tab opening app Y is already authenticated.
- Click logout in app X; confirm app Y now reports unauthenticated.

## Auth-flow note (reuse, don't reinvent)
Each app copies `app-alfred/alfred/auth/*` verbatim except: blueprint `url_prefix="/<slug>/auth"`, `AUTHLIB_CLIENT_ID` from config, and `SESSION_COOKIE_NAME` per app (distinct, so app-local sessions never collide — the bridge reads the *auth* cookie via `/auth/session/me`, not the app-local one). The landing page does NOT need its own OAuth client — it only builds a handoff URL to `/auth/login?next=/<slug>`; the app's own `/<slug>/auth/callback` completes the SSO and bridges the session via `_sync_profile_and_session`. Content APIs guard with `session["user_id"]` (None → 401/redirect). Cross-app SSO is delivered by the shared `nightcraft_auth_session` cookie + the per-app `before_request` bridge (see the Single Sign-On section above).

## Validation
1. **Local (no server):** each app `cd app-<x> && python -m venv .venv && pip install -r requirements.txt && AUTH_MODE=local FLASK_AUTH_MODE=local DATABASE_URL=sqlite:///test.db flask --app <pkg> setup && flask --app <pkg> run` → confirm `/<slug>/` landing renders, `/<slug>/app` requires login, model writes read back scoped to user.
2. **Landing:** `pytest app-landing/tests` — new `/quickposts` `/noteflow` `/scratchpad` render; `/experimental` lists all three with `/<slug>` URLs; deleted routes 404.
3. **Manifest/infra lint:** `bash -n` on every new `.sh`; `python3 platform-infra/prod-debian/scripts/products.py slugs --policy on_demand` lists the 6 on_demand apps; `python3 products.py get quickposts runtime.port` → `5310`.
4. **Server (post-deploy):** `sudo ./deploy-all.sh`; verify `systemctl status nightcraft-runtime-manager`, `nginx -t`, `curl -sI localhost/_nc_probe/quickposts` returns 404 (down) then after `curl -sI /quickposts/` the service auto-starts and the loader redirects into the app; DB roles `quickposts_app` etc. exist in Postgres.
5. **Cross-app SSO (must pass):** Log in once via `/auth/login` (or any existing app). In the same browser, open `/quickposts/app`, `/noteflow/app`, `/scratchpad/app` directly — each must show the authenticated UI with the correct `user_id` and **no** login redirect (proves the shared `nightcraft_auth_session` cookie + per-app bridge). Then POST `/auth/logout?next=/` and confirm all three apps report unauthenticated (unified logout).

## Open questions / risks
- **External CDNs in migrated HTML** (Tailwind CDN, Google Fonts, font-awesome, lucide) remain by design; the app UI requires outbound internet. Acceptable — matches current behavior. *(Resolved: keep CDN links.)*
- **Hard cutover** — `/quickpost`, `/miobook`, `/scrapbook` return 404 after this change; old bookmarks/links break by design. *(Resolved: no backward-compat redirects.)*
- **Idle timeout 15m** for all three apps (matches Green Pledge). *(Resolved.)*
- **DB passwords** are placeholders (`change_me`) in env examples; real values come from the deployed `/etc/nightcraft/app-<x>.env` (same convention as other apps).
- **Subpath SSO correctness**: verified `app-alfred/alfred/auth/sso_auth.py` already honors `X-Forwarded-Prefix`, so copying it with `url_prefix="/<slug>/auth"` round-trips the landing handoff `next=/<slug>` correctly. `guards.auth_required` is subpath-safe too.
- **No backend keepalive**: the three apps are stateless content editors; they do not need Alfred's run-keepalive timer. The runtime manager still stops them after 15m idle.
