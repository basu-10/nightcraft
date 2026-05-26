# SeekSage Backend

SeekSage backend is a Flask app with REST APIs and authentication. The UI migration from React/Vite to Flask templates is in progress.

## UI migration status

- Flask UI is now the default root experience at `/`.
- Flask UI remains directly accessible at `/ui`.
- Implemented in Flask UI:
  - `/ui/login`
  - `/ui/dashboard`
  - `/ui/notes`
  - `/ui/notifications`
  - `/ui/account`
  - `/ui/global-settings`
  - `/ui/admin`

## Run locally

```powershell
cd app-researchAgent/seeksage/backend
python run.py
```

Open:

- Flask UI (default): `http://127.0.0.1:5000/`
- Flask UI direct path: `http://127.0.0.1:5000/ui`

To temporarily disable root redirect and use legacy React dist at `/` when available:

```powershell
$env:SEEKSAGE_UI_AT_ROOT = "0"
python run.py
```

## Testing note

The current test harness requires `TEST_DATABASE_URL` to be set (PostgreSQL DSN) before running pytest.

```powershell
$env:TEST_DATABASE_URL = "postgresql://USER:PASS@127.0.0.1:5432/DB"
pytest -q
```
