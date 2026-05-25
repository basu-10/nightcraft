# Deploying to PythonAnywhere

## What changed to make this work on PythonAnywhere

PythonAnywhere runs your app as a WSGI process under uWSGI.  Three things in
the original architecture were incompatible:

| Problem | Fix |
|---|---|
| Background worker thread picking up queued runs | Removed. Runs now execute **synchronously** inside the HTTP request (≤ 5 min timeout). |
| Activity logger background writer thread | Replaced with direct synchronous writes to PostgreSQL. |
| LangGraph SqliteSaver writing to SQLite | Switched to an in-memory checkpointer per process. |

### What "synchronous execution" means for the frontend

`POST /api/sessions/<id>/runs` no longer returns immediately with
`status: "queued"`.  It now blocks until the agent finishes and returns
`status: "done"` (or `"error"`) along with `final_answer`.

The existing GET endpoints (`GET /api/runs/<id>` and
`GET /api/runs/<id>/events`) still work for history/replay.

---

## Setup steps

### 1. Create a PythonAnywhere account and web app

1. Sign up at https://www.pythonanywhere.com
2. **Web** tab → **Add a new web app** → select **Manual configuration** → **Python 3.12**

### 2. Upload / clone the project

In a PythonAnywhere Bash console:

```bash
cd ~
git clone <your-repo-url> seeksage
# or upload via Files tab
```

### 3. Create a virtualenv and install dependencies

```bash
mkvirtualenv --python=python3.12 seeksage
cd ~/seeksage/seeksage_webapp/backend
pip install -r requirements.txt
```

### 4. Initialise the database

```bash
cd ~/seeksage/seeksage_webapp/backend
export DATABASE_URL="postgresql://USER:PASSWORD@HOST:5432/nightcraft_seeksage"
flask db upgrade          # runs Alembic migrations
# Or, if you haven't set up migrations:
python -c "from app import create_app; app = create_app(); print('DB ok')"
```

### 5. Configure the WSGI file

In the **Web** tab, click the WSGI configuration file link and replace its
contents with the contents of `pythonanywhere_wsgi.py` from this folder,
filling in:

- `YOURUSER` — your PythonAnywhere username
- `YOURVENV`  — your virtualenv name (default: `seeksage`)
- `SECRET_KEY` — a long random string
- `CORS_ORIGINS` — your frontend URL (or `*` for development)

### 6. Static files (optional — if serving the built frontend)

Build the React frontend locally:

```bash
cd seeksage_webapp/frontend
npm ci && npm run build   # outputs to dist/
```

Upload `dist/` to PythonAnywhere, then in the **Web** tab add a static files
mapping:

| URL     | Directory                                    |
|---------|----------------------------------------------|
| `/app/` | `/home/YOURUSER/seeksage/seeksage_webapp/frontend/dist` |

### 7. Reload the web app

Click **Reload** in the Web tab.  Test with:

```
https://YOURUSER.pythonanywhere.com/api/health
```

Expected: `{"status": "ok"}`

---

## Environment variables reference

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SECRET_KEY` | yes | `dev-secret-key` | Set to a long random value in prod |
| `DATABASE_URL` | yes | none | PostgreSQL DSN for SeekSage backend |
| `CORS_ORIGINS` | no | `http://localhost:5173` | Comma-separated list of allowed origins |

---

## Limitations on the free PythonAnywhere tier

- **1 web app**, **500 MB storage**, **100 seconds CPU/day** for web tasks.
- No outbound internet access to arbitrary hosts on the free tier — you must
  **whitelist** OpenRouter (`openrouter.ai`) in the **Network** settings, or
  upgrade to a paid plan that allows unrestricted outbound connections.
- No always-on background tasks (paid tier only) — this is fine because we
  no longer need a background worker.
