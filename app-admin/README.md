# app-admin

Admin access handoff app for centralized authentication.

## What this app does

- Serves `/admin` behind nginx path routing
- Shows a login handoff page for admin access
- Redirects login to central auth with return path support (`next` by default)

## Local run

1. Create and activate a virtual environment.
1. Install dependencies:

```powershell
pip install -r requirements.txt
```

1. Start the app:

```powershell
python run.py
```

Default local URL: `http://127.0.0.1:5500`

## Environment variables

- `FLASK_ENV` (`development` or `production`)
- `FLASK_SECRET_KEY` (recommended in production)
- `FLASK_HOST` (default `127.0.0.1`)
- `FLASK_PORT` (default `5500`)
- `ADMIN_AUTH_URL` (default `/auth/login`)
- `ADMIN_AUTH_RETURN_PARAM` (default `next`)
- `ADMIN_RETURN_PATH` (default `/admin`)
