# Radio SSO Build and Integration Plan

This document defines how to build the missing `service-auth` SSO system and integrate it with `app-radio` while keeping standalone mode working.

## Goal

Enable `app-radio` to run in two auth modes:

- `AUTH_MODE=local`: standalone radio app, no external auth dependency
- `AUTH_MODE=sso`: radio app acts as an OAuth/OIDC client of `service-auth`

The migration is additive: local mode must remain stable while SSO mode is introduced.

## User Installation Paths

Keep these user choices intact:

### Users can choose

#### Option 1

Download only notes-app  
Run it standalone

#### Option 2

Download auth-service + notes-app  
Run with shared login

#### Option 3

Download nightcraft-server-stack  
Run the full ecosystem

### Radio App Interpretation

For radio users, apply the same pattern:

- Option 1 equivalent: download only `app-radio`, run standalone (`AUTH_MODE=local`)
- Option 2 equivalent: download `service-auth` + `app-radio`, run shared login (`AUTH_MODE=sso`)
- Option 3 equivalent: use `nightcraft-server-stack` for full multi-app ecosystem

## Current State (Verified)

### Already Complete in `app-radio`

- Auth adapter package exists: `devradio/auth/`
- Local and SSO auth paths are split (`local_auth.py`, `sso_auth.py`, `current_user.py`)
- Mode switch exists via `AUTH_MODE`
- `LoginManager` initialization is local-only
- Product user model split is done (`LocalCredential` + `UserProfile`)
- Guards are mode-agnostic (`auth_required`, `admin_required`)
- Template context uses `app_user`
- Authlib and PyJWT dependencies are present in `app-radio/requirements.txt`
- Route protection tests exist for `auth_required` in local and SSO modes

### Not Built Yet

- `service-auth` implementation (currently empty scaffold)
- Real OIDC metadata and token/userinfo endpoints
- SSO end-to-end tests and deployment wiring

## Target Architecture

### Service Roles

- `service-auth`: central identity provider (Authorization Server + OIDC Provider)
- `app-radio`: OAuth/OIDC client application

### Browser/Auth Flow

1. User opens radio protected route.
2. If unauthenticated, `app-radio` redirects to `service-auth` authorization endpoint.
3. User authenticates at `service-auth`.
4. `service-auth` redirects to `app-radio /auth/callback` with auth code.
5. `app-radio` exchanges code for tokens.
6. `app-radio` fetches/uses user claims, upserts `UserProfile`, creates local session.
7. User continues with radio app session cookie.

## Phase Plan

## Phase 1: Build `service-auth` MVP (OIDC Provider)

Create a production-oriented Flask service with these minimum endpoints:

- `/.well-known/openid-configuration`
- `/oauth/authorize`
- `/oauth/token`
- `/oauth/jwks`
- `/userinfo`
- `/login`, `/logout`, `/register` (or admin-seeded users initially)

Minimum data model in `service-auth` database:

- `users`
- `sessions`
- `oauth_clients`
- `authorization_codes`
- `refresh_tokens`

Recommended stack:

- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Authlib
- PyJWT

## Phase 2: Define Claim Contract

Finalize claim schema used by all client apps, including `app-radio`:

Required:

- `sub` (stable user id)
- `preferred_username`
- `email`

Optional/custom:

- `is_admin` (or roles/permissions alternative)
- `timezone_name`

Decision needed:

- Source of truth for admin authorization:
  - Option A: direct `is_admin` boolean claim
  - Option B: role claim (`roles: ["admin"]`) with client-side mapping

## Phase 3: Integrate `app-radio` with Real Metadata

Update `app-radio` config and behavior to consume real OIDC provider:

- Set `AUTH_SERVICE_URL` to deployed auth service base URL
- Register radio client in `service-auth` with:
  - `client_id`
  - `client_secret`
  - allowed `redirect_uri` list
- Verify callback URI alignment with reverse proxy pathing

In `app-radio` callback logic:

- Keep upsert into `UserProfile`
- Replace temporary claim assumptions with finalized mapping
- Ensure robust handling for missing optional claims

## Phase 4: Authorization Mapping in SSO Mode

Implement final admin strategy in adapter layer:

- Normalize claims to `AppUser` shape
- Store only product-specific projection in `UserProfile`
- Do not couple product logic directly to raw token payload

Add explicit fallback behavior when admin claim/role is absent.

## Phase 5: Tests

### `app-radio`

Add:

- `admin_required` tests in local mode
- `admin_required` tests in SSO mode
- SSO callback integration tests (token/userinfo mocked)

### `service-auth`

Add:

- authorization code flow tests
- discovery document tests
- JWKS/token signature validation tests
- client redirect URI validation tests

## Phase 6: Deployment Wiring (`nightcraft-server-stack`)

Compose and Nginx requirements:

- route `/auth` to `service-auth`
- ensure external URL consistency for discovery, issuer, and redirects
- propagate env vars into all services
- maintain per-app `AUTH_MODE` toggles

Required checks:

- redirect URI exact match in auth service client config
- cookie security flags and domain/path settings
- CSRF/state handling preserved through proxy

## Config Baseline

## `app-radio` env

```env
AUTH_MODE=local
AUTH_SERVICE_URL=http://localhost/auth
AUTHLIB_CLIENT_ID=radio-app
AUTHLIB_CLIENT_SECRET=dev-secret
```

Use `AUTH_MODE=sso` when `service-auth` is available.

## `service-auth` env (initial)

```env
FLASK_ENV=development
SECRET_KEY=change-me
DATABASE_URL=postgresql://auth_app:change_me@127.0.0.1:5432/auth_db
OIDC_ISSUER=http://localhost/auth
```

## Definition of Done

SSO integration is complete when all are true:

- `service-auth` serves valid OIDC discovery metadata
- radio login via auth code flow works end-to-end
- `UserProfile` upsert + local session creation succeeds
- `admin_required` behavior is tested and correct in both modes
- standalone (`AUTH_MODE=local`) still works unchanged
- full stack routing works behind Nginx/Compose

## Immediate Next Tasks

1. Scaffold `service-auth` Flask app with Authlib and migration support.
2. Implement discovery, authorize, token, jwks, userinfo endpoints.
3. Register `radio-app` client and validate callback flow locally.
4. Add missing `admin_required` tests in `app-radio`.
5. Add stack wiring tasks to `nightcraft-server-stack` once repo is ready.
