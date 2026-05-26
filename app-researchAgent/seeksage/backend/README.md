# SeekSage Backend

SeekSage backend is a Flask app with REST APIs and authentication. The UI migration from React/Vite to Flask templates is in progress.

## UI migration status

- Existing React frontend remains active at `/`.
- Flask migration preview lives under `/ui`.
- Implemented in Flask UI:
  - `/ui/login`
  - `/ui/dashboard`
  - `/ui/notes`
- Placeholder routes still pending migration:
  - `/ui/notifications`
  - `/ui/global-settings`
  - `/ui/account`
  - `/ui/admin`

## Run locally

```powershell
cd app-researchAgent/seeksage/backend
python run.py
```

Open:

- React app: `http://127.0.0.1:5000/`
- Flask UI preview: `http://127.0.0.1:5000/ui`

## Testing note

The current test harness requires `TEST_DATABASE_URL` to be set (PostgreSQL DSN) before running pytest.

```powershell
$env:TEST_DATABASE_URL = "postgresql://USER:PASS@127.0.0.1:5432/DB"
pytest -q
```
