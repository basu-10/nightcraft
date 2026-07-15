# service-auth (SSO Provider)

`service-auth` is the central auth service for the radio SSO migration. This initial milestone provides:

- Flask app factory and environment-based config
- SQLAlchemy + Flask-Migrate setup
- Core auth domain models (users, sessions, oauth clients, auth codes, refresh tokens)
- Health endpoint: `/healthz`
- OIDC discovery endpoint: `/.well-known/openid-configuration`
- JWKS endpoint: `/oauth/jwks`
- Session-backed auth UI endpoints: `/register`, `/login`, `/logout`
- Shared auth UI now mirrors the radio app's login card styling and includes Google sign-in support
- Post-login `next` URLs are preserved for cross-app destinations; `X-Forwarded-Prefix` is applied only to auth-internal paths such as `/oauth/`, `/login`, `/register`, `/logout`, `/session/`, and `/healthz`
- OAuth authorization endpoint: `/oauth/authorize`
- OAuth token endpoint: `/oauth/token`
- User claims endpoint: `/userinfo`
- Session introspection endpoint for shared-cookie apps: `/session/me`
- RS256 signing with generated keypair persisted under `instance/keys` by default

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

Or use the Windows helper script:

```powershell
.\dev-start.ps1
```

Script options:

```powershell
.\dev-start.ps1 -Seed -RedirectUri http://127.0.0.1:5000/auth/callback
```

1. (Optional) Copy env template:

```powershell
copy .env.example .env
```

1. Set `DATABASE_URL` in `.env` to a PostgreSQL DSN.
	Example: `postgresql://postgres:postgres@localhost:5432/nightcraft_auth`

1. Start service:

```powershell
python run.py
```

Default URL: `http://localhost:5100`

## Endpoints Available Now

- `GET /`
- `GET /healthz`
- `GET /.well-known/openid-configuration`
- `GET /oauth/jwks`
- `GET|POST /register`
- `GET|POST /login`
- `POST /logout`
- `GET /oauth/authorize`
- `POST /oauth/token`
- `GET /userinfo`
- `GET /session/me`

## Post-Login Redirect Normalization

`service-auth` accepts a `next` query/form value from app login handoffs and preserves it after successful registration, login, or Google callback.
The redirect target must be path-relative; absolute URLs and open redirects are rejected and replaced with the safe default target.
When nginx sets `X-Forwarded-Prefix: /auth`, the prefix is applied only to auth-internal paths such as `/oauth/`, `/login`, `/register`, `/logout`, `/session/`, and `/healthz`.
Cross-app destinations such as `/neera/me` or `/notestack/app` are left intact so the OIDC callback can return users to the original product route.

## Migration Workflow (Flask-Migrate)

Initialize migrations once:

```powershell
flask --app run.py db init
```

Create migration after model changes:

```powershell
flask --app run.py db migrate -m "Describe change"
```

Apply migration:

```powershell
flask --app run.py db upgrade
```

## App Integrations

Example SSO client configuration:

```env
FLASK_AUTH_MODE=sso
FLASK_AUTH_SERVICE_URL=http://localhost:5100
FLASK_AUTHLIB_CLIENT_ID=radio-app
FLASK_AUTHLIB_CLIENT_SECRET=dev-secret
```

Current claim contract returned by `/userinfo` includes: `sub`, `preferred_username`, `email`, `is_admin`, `timezone_name`.

Finalized admin contract:

- `roles` is the canonical authorization claim.
- Admin access is granted when `roles` contains `admin`.
- `is_admin` remains present as a derived compatibility claim.
- `timezone_name` remains optional for consumers and defaults to `Asia/Kolkata`.

Current `/userinfo` and ID token claims include: `sub`, `preferred_username`, `email`, `roles`, `is_admin`, `timezone_name`.

The persisted `users` table only stores `username`, `email`, `password_hash`, `is_admin`, and `timezone_name`. Google sign-in reuses those columns instead of introducing a separate external-identity table.

Access tokens and ID tokens are signed with `RS256` using a local keypair. The public key is exposed through `/oauth/jwks`.

## Google Sign-In (Optional)

To enable the shared login page's Google button, set:

```env
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_DISCOVERY_URL=https://accounts.google.com/.well-known/openid-configuration
```

## Local Dev Seeding

Create a default user and OAuth client for a client app integration:

```powershell
flask --app run.py seed-dev
```

Useful overrides:

```powershell
flask --app run.py seed-dev --username devuser --email devuser@example.com --password devpass123 --client-id radio-app --client-secret dev-secret --redirect-uri http://127.0.0.1:5000/auth/callback
```

Seed one user-role account and one admin-role account:

```powershell
flask --app run.py seed-role-users
```

Useful overrides:

```powershell
flask --app run.py seed-role-users --user-username seeduser --user-email seeduser@example.com --user-password seeduser123 --admin-username seedadmin --admin-email seedadmin@example.com --admin-password seedadmin123
```
