# app-landing

Landing app for the multi-product portfolio hub.

## What this app does

- Serves the root route (`/`) as a product launchpad
- Uses a clean index-style homepage layout with search bar, philosophy panel, and product registry rows
- Links to DevRadio, NEERA, NoteStack, central auth sign-in/sign-up, and admin
- Serves a central admin entry page at `/platform-admin` for cross-product admin navigation
- Shows a welcome banner (`Hi, <username> welcome`) when the shared auth session is active
- Keeps sign-in and sign-up entry points on the landing homepage
- Keeps product URLs configurable through environment variables

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

Default local URL: `http://127.0.0.1:5400`

## Environment variables

- `FLASK_ENV` (`development` or `production`)
- `FLASK_SECRET_KEY` (recommended in production)
- `FLASK_HOST` (default `127.0.0.1`)
- `FLASK_PORT` (default `5400`)
- `LANDING_AUTH_URL` (default `/auth/login`)
- `LANDING_LOGOUT_URL` (default `/auth/logout`)
- `LANDING_AUTH_SESSION_ME_URL` (default `/auth/session/me`)
- `LANDING_AUTH_RETURN_PARAM` (default `next`)
- `LANDING_ADMIN_URL` (default `/platform-admin`)
- `LANDING_DEVRADIO_URL` (default `/devradio`)
- `LANDING_NEERA_URL` (default `/neera`)
- `LANDING_NOTESTACK_URL` (default `/notestack`)
- `LANDING_FOSSIL_URL` (default `/fossil`)
- `LANDING_FOSSIL_GITHUB_URL` (default empty; FOSSil "View on GitHub"/Docs links fall back to `LANDING_FOSSIL_URL`)
- `LANDING_FOSSIL_DOWNLOAD_URL` (default empty; FOSSil "Download" links fall back to `LANDING_FOSSIL_URL`)
- `LANDING_TEXTTRACE_URL` (default `/texttrace`)
- `LANDING_TEXTTRACE_GITHUB_URL` (default empty; TextTrace GitHub/Docs links fall back to `LANDING_TEXTTRACE_URL`)
- `LANDING_TEXTTRACE_DOWNLOAD_URL` (default empty; TextTrace download links fall back to `LANDING_TEXTTRACE_URL`)

## Tests

```powershell
pytest tests
```
