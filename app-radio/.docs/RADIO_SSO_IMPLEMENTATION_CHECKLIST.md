# Radio SSO Implementation Checklist (Issue-by-Issue)

Source: RADIO_SSO_BUILD_AND_INTEGRATION_PLAN.md

This checklist converts the migration plan into executable issues for building service-auth and integrating app-radio.

## Execution Order

1. Build service-auth scaffold and persistence foundation.
2. Implement OIDC endpoints in strict order.
3. Define and lock claim contract.
4. Integrate app-radio with real service-auth metadata.
5. Implement final authorization mapping.
6. Complete test matrix across service-auth and app-radio.
7. Wire deployment in nightcraft-server-stack.

## Current Implementation Status (Updated: 2026-05-21)

Legend: `COMPLETE`, `PARTIAL`, `NOT STARTED`

| Issue | Status | Notes |
| --- | --- | --- |
| 1 - Scaffold service-auth Flask project | COMPLETE | App factory, config classes, extensions, health endpoint, and README are implemented. |
| 2 - Add auth service dependencies and migrations | COMPLETE | Dependencies and Flask-Migrate wiring are in place; migration commands are documented. |
| 3 - Implement core auth data model | COMPLETE | `users`, `sessions`, `oauth_clients`, `authorization_codes`, `refresh_tokens` models exist with constraints/indexed lookup fields. |
| 4 - Implement OIDC discovery endpoint | COMPLETE | `/.well-known/openid-configuration` implemented and covered by tests. |
| 5 - Implement JWKS endpoint and key management | COMPLETE | RS256 keypair generation/loading implemented; `/oauth/jwks` returns active key with `kid`; signing uses matching keypair. |
| 6 - Implement login/logout/register UI and session foundation | COMPLETE | `/login`, `/logout`, `/register` implemented with session-backed login flow and test coverage. |
| 7 - Implement authorize endpoint | COMPLETE | `/oauth/authorize` validates client/redirect/response type/scope and issues short-lived code with state passthrough. |
| 8 - Implement token endpoint | COMPLETE | `/oauth/token` validates client + code integrity/expiry/reuse and returns access token, id token, refresh token. |
| 9 - Implement userinfo endpoint | COMPLETE | `/userinfo` validates bearer token and returns finalized claims. |
| 10 - Finalize claim contract and admin mapping strategy | COMPLETE | Claim contract is now roles-first: `sub`, `preferred_username`, `email`, `roles`, optional derived `is_admin`, and optional `timezone_name`. App-radio admin access is derived from the presence of `admin` in `roles`. |
| 11 - Integrate app-radio with real service-auth metadata | PARTIAL | SSO adapter points to discovery metadata; dev startup supports SSO env wiring; seed CLI creates `radio-app` client. Full browser e2e verification of live login flow remains pending. |
| 12 - Implement final app-radio authorization mapping | COMPLETE | Callback upserts `UserProfile`, handles missing token userinfo by calling `/userinfo`, and applies admin mapping with fallback behavior. |
| 13 - Add missing app-radio tests | COMPLETE | Callback integration tests cover roles-first admin mapping, derived `is_admin` fallback, invalid callback state, and `admin_required` local+SSO coverage. |
| 14 - Add service-auth test suite | PARTIAL | Discovery, authorize, token, userinfo, redirect mismatch, invalid client, code reuse, and roles-first claim contract tests are implemented. Live browser/proxy state replay coverage still remains outside the provider unit suite. |
| 15 - Deployment wiring in nightcraft-server-stack | NOT STARTED | Reverse proxy and compose/env propagation work has not been implemented yet. |

### Milestone Progress Snapshot

- Milestone 1 (Issues 1-3): COMPLETE
- Milestone 2 (Issues 4-9): COMPLETE
- Milestone 3 (Issues 10-12): COMPLETE
- Milestone 4 (Issues 13-14): PARTIAL
- Milestone 5 (Issue 15): NOT STARTED

### Most Important Remaining Work

1. Run and document full browser e2e SSO validation for app-radio against live service-auth (Issue 11).
2. Complete deployment wiring in `nightcraft-server-stack` (Issue 15).
3. Add proxy-level validation for callback state/cookie behavior under the final deployment topology (Issue 14/15).

## Issue 1 - Scaffold service-auth Flask project

Objective:
Create the initial runnable auth service structure with app factory, config loading, and package layout.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Create service-auth application package and app factory.
- Add config classes (dev/test/prod) and env loading.
- Add extensions bootstrap (db, migrate, authlib integration hooks).
- Add health endpoint for startup validation.
- Add README with run commands and environment variables.

Acceptance criteria:
- service-auth starts locally with one command.
- Health endpoint returns 200.
- Config switches by environment.

Depends on:
- None

## Issue 2 - Add auth service dependencies and migrations

Objective:
Prepare database and migration workflow for auth domain models.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Add requirements in service-auth requirements file:
  - flask>=2.3.0
  - flask-sqlalchemy>=3.0.0
  - authlib>=1.2.0
  - flask-migrate>=4.0.0
  - pyjwt>=2.8.0
- Initialize migration support.
- Add migration commands documentation.

Acceptance criteria:
- Fresh database can be created and migrated from scratch.
- Migration command sequence is documented and repeatable.

Depends on:
- Issue 1

## Issue 3 - Implement core auth data model

Objective:
Create minimum persistence model for auth code flow.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Add tables:
  - users
  - sessions
  - oauth_clients
  - authorization_codes
  - refresh_tokens
- Add indexes for lookup paths (client id, user id, code/token ids).
- Add model constraints for redirect URI and client uniqueness.

Acceptance criteria:
- All required tables exist after migration.
- Basic CRUD works in local dev.

Depends on:
- Issue 2

## Issue 4 - Implement OIDC discovery endpoint

Objective:
Expose service metadata as the first contract consumed by clients.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoint:
- /.well-known/openid-configuration

Checklist:
- Return issuer, authorization endpoint, token endpoint, jwks URI, userinfo endpoint, supported scopes and response types.
- Ensure URLs are externally correct when behind proxy.

Acceptance criteria:
- Endpoint returns valid JSON and 200.
- app-radio can resolve metadata URL from AUTH_SERVICE_URL.

Depends on:
- Issue 1

## Issue 5 - Implement JWKS endpoint and key management

Objective:
Expose signing keys for token verification.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoint:
- /oauth/jwks

Checklist:
- Add key generation/loading strategy for development and production.
- Return JWKS payload.
- Ensure key id usage supports future rotation.

Acceptance criteria:
- JWKS endpoint returns valid key set.
- Tokens signed by service-auth can be verified against JWKS.

Depends on:
- Issue 4

## Issue 6 - Implement login/logout/register UI and session foundation

Objective:
Provide minimal user interaction layer for auth flow completion.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoints:
- /login
- /logout
- /register (or admin-seeded user path)

Checklist:
- Add credential validation for local auth service users.
- Create service-auth session cookie behavior.
- Support authenticated session reuse for SSO across client apps.

Acceptance criteria:
- User can register/login/logout in dev setup.
- Existing service-auth session skips repeated credential prompts.

Depends on:
- Issue 3

## Issue 7 - Implement authorize endpoint

Objective:
Issue authorization codes after validating user session and client request.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoint:
- /oauth/authorize

Checklist:
- Validate client id, redirect URI, response type, scope, state.
- Enforce login requirement with redirect to login endpoint.
- Generate short-lived authorization code bound to client and user.

Acceptance criteria:
- Valid authorize request redirects with code and state.
- Invalid redirect URI is rejected.

Depends on:
- Issue 6
- Issue 3

## Issue 8 - Implement token endpoint

Objective:
Exchange authorization code for access and id token.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoint:
- /oauth/token

Checklist:
- Validate client credentials and grant type.
- Validate authorization code integrity, expiry, and one-time use.
- Issue id token with finalized claims.
- Issue access token (and refresh token if enabled).

Acceptance criteria:
- Code exchange returns expected token payload for valid request.
- Reused/expired/invalid code is rejected.

Depends on:
- Issue 7
- Issue 5

## Issue 9 - Implement userinfo endpoint

Objective:
Serve claims to clients using access token.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Endpoint:
- /userinfo

Checklist:
- Validate bearer token.
- Return finalized claim set.
- Keep claim mapping consistent with id token.

Acceptance criteria:
- Valid access token returns expected user claims.
- Invalid token returns authorization error.

Depends on:
- Issue 8

## Issue 10 - Finalize claim contract and admin mapping strategy

Objective:
Lock cross-app claims contract, including admin policy.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Decide one admin strategy:
  - Option A: is_admin boolean
  - Option B: roles array with admin role mapping
- Finalize required claims:
  - sub
  - preferred_username
  - email
- Finalize optional claims:
  - timezone_name
  - derived is_admin
  - roles
- Publish contract in service-auth docs.

Acceptance criteria:
- Contract is documented and approved.
- app-radio can implement stable mapping without temporary assumptions.

Depends on:
- Issue 8
- Issue 9

## Issue 11 - Integrate app-radio with real service-auth metadata

Objective:
Connect app-radio SSO path to live service-auth endpoints.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Register radio-app client in service-auth with correct redirect URIs.
- Set AUTH_SERVICE_URL, AUTHLIB_CLIENT_ID, AUTHLIB_CLIENT_SECRET in app-radio env.
- Verify app-radio auth callback uses real token/userinfo data.
- Keep AUTH_MODE=local unchanged and functional.

Acceptance criteria:
- AUTH_MODE=sso login works end-to-end.
- AUTH_MODE=local still works without service-auth.

Depends on:
- Issue 4 through Issue 10

## Issue 12 - Implement final app-radio authorization mapping

Objective:
Remove temporary claim assumptions and finalize product-level user projection.

Status tracker:
- [x] Complete
- [ ] Partial / In progress
- [ ] Not started

Checklist:
- Update callback mapping to use finalized claim contract.
- Implement explicit fallback behavior for missing optional claims.
- Persist only required product projection in UserProfile.

Acceptance criteria:
- UserProfile upsert is stable for both new and returning SSO users.
- admin_required behavior reflects final policy.

Depends on:
- Issue 10
- Issue 11

## Issue 13 - Add missing app-radio tests

Objective:
Close known coverage gaps in radio app.

Status tracker:
- [ ] Complete
- [x] Partial / In progress
- [ ] Not started

Checklist:
- Add admin_required tests in local mode.
- Add admin_required tests in SSO mode.
- Add auth callback integration tests with mocked token/userinfo flows.

Acceptance criteria:
- New tests pass consistently in CI/dev.
- Regressions in role handling are detected by tests.

Depends on:
- Issue 12

## Issue 14 - Add service-auth test suite

Objective:
Validate protocol correctness and security boundaries.

Status tracker:
- [ ] Complete
- [x] Partial / In progress
- [ ] Not started

Checklist:
- Add discovery document tests.
- Add authorization code flow tests.
- Add JWKS and token signature tests.
- Add redirect URI validation tests.
- Add negative tests for invalid client, invalid state, invalid code reuse.

Acceptance criteria:
- All core auth endpoints have success and failure tests.
- Token and redirect security checks are enforced by tests.

Depends on:
- Issue 4 through Issue 9

## Issue 15 - Deployment wiring in nightcraft-server-stack

Objective:
Enable production-like full ecosystem routing and environment propagation.

Status tracker:
- [ ] Complete
- [ ] Partial / In progress
- [x] Not started

Checklist:
- Add /auth reverse proxy route to service-auth.
- Ensure consistent issuer and external URL pathing.
- Propagate AUTH_MODE and OIDC vars to relevant app services.
- Validate redirect URI and callback URI under proxy.
- Validate cookie flags and CSRF/state behavior through proxy.

Acceptance criteria:
- Full stack boots and SSO works through Nginx.
- No redirect mismatch errors under external URL.

Depends on:
- Issue 11
- Issue 14

## OIDC Endpoint Build Order (Strict)

1. /.well-known/openid-configuration
2. /oauth/jwks
3. /login, /logout, /register
4. /oauth/authorize
5. /oauth/token
6. /userinfo

Rationale:
- Discovery and keys must exist before client integration.
- User session/login must exist before authorization.
- Authorization must exist before token exchange.
- Userinfo depends on token issuance.

## Test Matrix

## A) service-auth endpoint matrix

- Discovery endpoint:
  - 200 response, required fields present, external URLs correct.
- JWKS endpoint:
  - valid JWK schema, key id present, rotation compatibility.
- Login/register/logout:
  - successful login path, invalid credentials rejection, session persistence.
- Authorize endpoint:
  - valid request returns code/state.
  - invalid redirect URI rejected.
  - unauthenticated user redirected to login.
- Token endpoint:
  - valid code exchange succeeds.
  - invalid/reused/expired code rejected.
  - invalid client auth rejected.
- Userinfo endpoint:
  - valid bearer token returns expected claims.
  - invalid token rejected.

## B) app-radio matrix

- Local mode:
  - auth_required redirects unauthenticated user.
  - admin_required allows admin, blocks listener/anonymous.
- SSO mode:
  - auth_required redirects when no session.
  - callback creates/updates UserProfile.
  - admin_required follows finalized claim mapping.
  - missing optional claims use fallback values.
- Regression:
  - AUTH_MODE=local unaffected by SSO implementation.
  - template app_user remains mode-agnostic.

## C) end-to-end matrix (service-auth + app-radio)

- Fresh user login through service-auth to radio protected route.
- Returning user with existing auth service session gets silent SSO.
- Logout behavior validated (service-auth and app local session expectations).
- Reverse proxy pathing validated under /auth and radio route.

## D) security and reliability matrix

- state parameter replay/validation checks.
- redirect URI exact matching.
- token signature verification against JWKS.
- secure cookie attributes for target environment.
- expired code/token handling.

## Suggested Milestone Grouping

Milestone 1 (Auth service foundation): Issue 1-3  
Milestone 2 (OIDC protocol endpoints): Issue 4-9  
Milestone 3 (Contract + app integration): Issue 10-12  
Milestone 4 (Test completion): Issue 13-14  
Milestone 5 (Full stack deployment): Issue 15
