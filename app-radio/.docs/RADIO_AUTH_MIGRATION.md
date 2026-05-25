# Radio App Auth Migration Delivery Tracker

Using Authlib for both client and server-side OAuth/OIDC.

## Completed Work Log

### Delivery Summary

- Auth adapter package is in place and mode-aware: `devradio/auth/` with `local_auth.py`, `sso_auth.py`, and `current_user.py`
- `AUTH_MODE` config is active; `LoginManager` initialization is conditional and local-only
- Auth model split is complete:
  - `LocalCredential` stores local auth credentials
  - `UserProfile` stores product-level user data for both auth modes
  - `SavedStory.user_id` now points to `UserProfile.id`
- Guards are mode-agnostic:
  - `guards.py` now resolves users via `get_current_user()`
  - Added `auth_required` and migrated protected app routes from `@login_required` to `@auth_required`
- Templates are mode-agnostic via injected `app_user` context
- SSO callback path currently upserts `UserProfile` and stores session fields from the persisted profile
- Regression coverage added for route protection in local and SSO modes (`tests/test_auth_required.py`)

### Completed Milestones

| # | Area | Delivery | Status |
|---|---|---|---|
| 1 | Phase 1 | Create `devradio/auth/` package and move local blueprint to `local_auth.py` | Done |
| 2 | Phase 1 | Add `current_user.py` adapter for local + SSO user resolution | Done |
| 3 | Phase 1 | Add auth package bootstrap selected by `AUTH_MODE` | Done |
| 4 | Phase 3 | Refactor `guards.py` to use `get_current_user()` | Done |
| 5 | Phase 2 | Split `User` into `LocalCredential` + `UserProfile`; update `SavedStory` FK | Done |
| 6 | Phase 4 | Conditionalize `LoginManager` initialization in `create_app()` | Done |
| 7 | Phase 5 | Add `sso_auth.py` OAuth client setup scaffold | Done (stub/integration-ready) |
| 8 | Phase 5 | Decouple templates/views from direct flask-login `current_user.*` usage | Mostly done |
| 9 | Extra | Add `auth_required` and migrate protected routes | Done |
| 10 | Extra | Add auth guard regression tests | Done |

### Deployment Modes Confirmed

| Scenario | Mode | Requirement |
|---|---|---|
| Standalone radio app | `AUTH_MODE=local` | No external auth service required |
| Radio + auth service | `AUTH_MODE=sso` | `service-auth` with OIDC endpoints |
| Full ecosystem (`nightcraft-server-stack`) | Both modes | nginx + compose wiring + auth service + clients |

### Key Stability Note

- The migration kept `AUTH_MODE=local` behavior stable while making SSO additive.

---

## Remaining Work Checklist

### Core Integration

- [ ] Integrate with real `service-auth` OIDC metadata and endpoints
- [ ] Validate full auth code flow end-to-end (login, callback, token exchange, userinfo, session)
- [ ] Replace temporary session claim assumptions with finalized claim mapping from `service-auth`

### Authorization

- [ ] Define SSO admin authorization source of truth (`is_admin` mapping strategy)
- [ ] Implement admin mapping in SSO mode in the auth adapter path

### Test Coverage

- [ ] Add tests for `admin_required` behavior in local mode
- [ ] Add tests for `admin_required` behavior in SSO mode
- [ ] Add end-to-end auth callback tests for SSO mode once `service-auth` is live

### Deployment/Wiring

- [ ] Finalize `nightcraft-server-stack` wiring for `AUTH_MODE=sso`
- [ ] Confirm environment variable propagation across services
- [ ] Verify redirect URIs and callback URLs in nginx/proxy setup

### Dependencies

- [ ] Ensure `app-radio/requirements.txt` includes:

```txt
authlib>=1.2.0
PyJWT>=2.8.0
```

- [ ] When `service-auth` is implemented, ensure `service-auth/requirements.txt` includes:

```txt
flask>=2.3.0
flask-sqlalchemy>=3.0.0
authlib>=1.2.0
flask-migrate>=4.0.0
PyJWT>=2.8.0
```

### Config Baseline

- [ ] Confirm `.env` / config defaults are present and environment-specific overrides are set:

```python
# Auth mode: "local" or "sso"
AUTH_MODE = os.getenv("AUTH_MODE", "local")

# SSO only:
AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://localhost/auth")
AUTHLIB_CLIENT_ID = os.getenv("AUTHLIB_CLIENT_ID", "radio-app")
AUTHLIB_CLIENT_SECRET = os.getenv("AUTHLIB_CLIENT_SECRET", "dev-secret")
```
