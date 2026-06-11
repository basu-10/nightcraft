# NoteStack Web

Companion web app for NoteStack desktop. Edit notes in the browser with the Lexical editor and sync them back to your Windows machine — offline-first, file-based, conflict-aware.

In the Nightcraft stack, this app is mounted under `/notestack` and uses shared session login from `service-auth` when `AUTH_MODE=sso`.

Guest mode is enabled by default on `/app`: when no authenticated session exists, the app runs fully in browser-only mode and stores notes/folders/tags in IndexedDB on the client device.

Guest mode data tools:

- Export guest data to a JSON backup from the sidebar.
- Import a JSON backup back into guest mode on the same or another browser.
- After sign-in, if guest data exists in that browser, NoteStack prompts to import it into the authenticated account and then clears local guest data.

Database backend note:

- Current default is `sqlite` for backward compatibility.
- PostgreSQL migration is in progress. See `POSTGRES_MIGRATION_PLAN.md`.

---

## Project structure

```text
app-note/
  app/
    __init__.py        # Flask app factory
    database.py        # DB schema + CRUD / sync helpers (sqlite default, postgres in progress)
    auth/routes.py     # local auth mode
    auth/sso_auth.py   # shared-auth session bridge mode
    api/routes.py      # /api   — CRUD + sync push/pull/conflicts
    main/routes.py     # /      — SPA shell + settings page
    templates/         # Jinja2 templates
  static/
    css/style.css      # Dark theme matching desktop palette
    js/app.js          # Main SPA logic
    js/guest_store.js  # IndexedDB local API adapter for guest mode
    js/lexical_editor.js  # Lexical editor integration
    js/conflicts.js    # Conflict resolution UI
    js/lexical_editor/ # Lexical helper modules (toolbar, nodes, insertions)
  config.py            # DevelopmentConfig / ProductionConfig
  run.py               # Local dev server
  wsgi.py              # WSGI entry point
```

---

## Local development

### 1. Prerequisites

Python 3.11+

### 2. Create & activate a venv

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Set required environment variables

```powershell
$env:FLASK_SECRET_KEY = "change-me-to-something-long-and-random"
# Optional backend selector: sqlite (default) or postgres
$env:NOTESTACK_DB_BACKEND = "sqlite"
# Optional — defaults to app-note/notestack.db
$env:NOTESTACK_DB = "D:\dev_work\web_dev\personal site\ionos-server\app-note\notestack.db"
# Required only when NOTESTACK_DB_BACKEND=postgres
# $env:DATABASE_URL = "postgresql://notestack_app:change_me@127.0.0.1:5432/notestack_db"
```

### 4. Run

```powershell
cd app-note
python run.py
```

Open `http://127.0.0.1:5335` in a browser and go to `/app` to start in guest mode.
Sign in/register when you want account-backed sync and token settings.

For shared-auth development against `service-auth`:

```powershell
$env:AUTH_MODE = "sso"
$env:AUTH_SERVICE_URL = "http://127.0.0.1:5100"
```

---

## Production stack deployment

Nightcraft production mounts NoteStack at `http://31.70.85.89/notestack`.

Required production env values:

```env
FLASK_ENV=production
FLASK_SECRET_KEY=change-me
FLASK_SESSION_SECURE=1
AUTH_MODE=sso
AUTH_SERVICE_URL=http://31.70.85.89/auth
SESSION_COOKIE_PATH=/notestack
NOTESTACK_DB_BACKEND=postgres
DATABASE_URL=postgresql://notestack_app:change_me@127.0.0.1:5432/notestack_db
LOCALAPPDATA=/runtime/shared/app-note/localappdata
```

Production deploy notes:

- `deploy-note.sh` requires `NOTESTACK_DB_BACKEND=postgres`.
- If `DATABASE_URL` is absent, the deploy script derives it from the default NoteStack role/database/password and writes it back to `/etc/nightcraft/app-note.env`.
- Runtime app data and sync logs are kept under `/runtime/shared/app-note/`, outside the source checkout.
- Sync logging writes to `LOCALAPPDATA/ABasu_apps/NoteStack/sync.log` and ignores directory/file creation failures; the `/sync-log` page returns an empty response instead of 502 when the log cannot be read.

Desktop clients should use the value shown in `/settings`:

- Server URL: `http://31.70.85.89/notestack`
- API Token: generated from the NoteStack settings page

## Standalone deployment

### 1. Upload / clone the repository

In a PythonAnywhere bash console:

```bash
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git ~/notestack
```

### 2. Create a virtualenv

```bash
mkvirtualenv notestack --python=python3.11
pip install -r ~/notestack/app-note/requirements.txt
```

### 3. Create the web app (manual WSGI)

- Go to **Web** tab → **Add a new web app** → **Manual configuration** → Python 3.11.
- Set the **Source code** directory to `/home/YOUR_USERNAME/notestack`.
- Set the **Virtualenv** to `/home/YOUR_USERNAME/.virtualenvs/notestack`.

### 4. Edit the WSGI file

Replace the default WSGI file content with:

```python
import sys, os
sys.path.insert(0, '/home/YOUR_USERNAME/notestack')
os.environ['FLASK_ENV'] = 'production'
os.environ['FLASK_SECRET_KEY'] = 'CHANGE_ME_TO_SOMETHING_LONG_AND_RANDOM'
os.environ['NOTESTACK_DB_BACKEND'] = 'sqlite'
os.environ['NOTESTACK_DB'] = '/home/YOUR_USERNAME/notestack_data/notestack.db'
from app import create_app
application = create_app()
```

> Create the data directory first: `mkdir ~/notestack_data`

### 5. Static files

In the PythonAnywhere **Web** tab under **Static files**, add:

| URL        | Directory                                       |
| ---------- | ----------------------------------------------- |
| `/static/` | `/home/YOUR_USERNAME/notestack/app-note/static` |

### 6. Reload the web app

Click **Reload** in the Web tab. Your app will be live at `YOUR_USERNAME.pythonanywhere.com`.

---

## Desktop sync setup

1. In the web app go to `/settings` → generate an **API Token** and copy it.

1. In NoteStack desktop open **Settings** → **SYNC** section:

- **Server URL**: `https://YOUR_USERNAME.pythonanywhere.com`
- **API Token**: paste the token you copied
- Check **Enable background sync**
- Click **Save sync settings**

1. The desktop will pull notes on startup and push 3 seconds after each save. The tray icon tooltip reflects sync status.

### Conflict resolution

If a note is edited on both the web and the desktop between syncs, a conflict is recorded server-side. A warning banner appears in the web app. Click it to open the side-by-side diff and choose which version to keep (or merge them manually).

---

## Sync protocol summary

| Operation     | Trigger                           | Endpoint                                |
| ------------- | --------------------------------- | --------------------------------------- |
| Push          | 3s after any note save on desktop | `POST /api/sync/push`                   |
| Pull          | App startup                       | `GET /api/sync/pull?since=<ISO>`        |
| Conflict list | Web banner / desktop tray         | `GET /api/sync/conflicts`               |
| Resolve       | Web UI                            | `POST /api/sync/conflicts/<id>/resolve` |

Conflict detection: a conflict is raised when the server's `updated_at > client_updated_at` (the web app edited the note after the desktop's last successful push).

## Sync Logging Hardening

Sync logging uses `LOCALAPPDATA/ABasu_apps/NoteStack/sync.log` on the server.
Directory creation and log-file creation failures are ignored so sync requests do not fail because the runtime log path is temporarily unavailable.
The `/sync-log` route returns an empty response if the file cannot be read, avoiding 502 responses during transient filesystem/OSError conditions.

---

## Security notes

- Passwords are hashed with `werkzeug.security` (PBKDF2-SHA256).
- API tokens are `secrets.token_urlsafe(32)` and stored in the app database for bearer-token sync auth.
- Login authentication is local `username + password` in local mode, or shared session login via `service-auth` in `AUTH_MODE=sso`.
- Multiple accounts can share the same email address; username remains globally unique.
- `SESSION_COOKIE_SECURE` is `True` in production (HTTPS on PythonAnywhere).
- `SESSION_COOKIE_HTTPONLY` and `SESSION_COOKIE_SAMESITE="Lax"` are always set.
