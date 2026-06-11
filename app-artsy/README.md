# NEERA

NEERA is the arts-focused app in this federated portable apps workspace.

## Runtime Modes

- Standalone mode
  - Local auth lives inside NEERA
  - App data is stored in PostgreSQL via DATABASE_URL
  - Started from app-local scripts
- Shared SSO mode
  - service-auth owns login and OIDC flows
  - NEERA is an OIDC client and stores product data in PostgreSQL

## Quick Start

Standalone local mode:

```powershell
.\dev-start.ps1
```

Shared SSO mode:

```powershell
.\dev-start.ps1 -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100 -AuthClientId neera-app -AuthClientSecret dev-secret
```

## Setup And Run Manually

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/nightcraft_neera"
.\.venv\Scripts\python.exe -m flask --app neera setup
.\.venv\Scripts\python.exe -m flask --app neera run --port 5600
```

## OIDC Notes

In shared mode, the login UI is served by service-auth and NEERA redirects to /auth/login.

NEERA expects these claims from service-auth:

- sub
- preferred_username
- email
- roles
- optional derived is_admin

NEERA persists app-specific profile data in PostgreSQL.

When `AUTH_MODE=sso`, NEERA now also attempts shared-session bootstrap via
`/session/me` before each request. If the user already logged in on the landing
page, NEERA hydrates local profile/session state automatically and opens with the
user already signed in.

NEERA also exposes a basic admin page at `GET /admin` (admin role only) with
summary counts for profiles, works, reviews, lists, and notes.

## Profile Header Editing

Authenticated users can now edit their profile header directly from their profile page.

- Route: POST /me/profile
- Editable fields:
  - location
  - profile_link
  - avatar_url
  - background_url
- URL validation: link and image fields must start with http:// or https://
- Tabs contract: Bookmarks tab is visible only to the profile owner

Because NEERA is still in active development, schema changes may require recreating the local development PostgreSQL database.

## Profile Tab Routes

NEERA now has real routes for the tabbed profile interface.

- Public profile tabs:
  - GET /u/{username}
  - GET /u/{username}/lists
  - GET /u/{username}/notes
  - GET /u/{username}/feed
- Owner-only routes:
  - GET /u/{username}/drafts (returns 404 for non-owners)
  - GET /me/drafts (owner convenience redirect)
  - GET /u/{username}/bookmarks (returns 404 for non-owners)
  - GET /me/bookmarks (owner convenience redirect)

## Item-Centric Foundation

Issue 16/17 foundation now includes the normalized work schema, active catalog seeding, and the initial item page contract.

- Seed command:

```powershell
.\.venv\Scripts\python.exe -m flask --app neera seed-catalog
```

- The seed command now inserts the prepared catalog dataset from `neera/catalog_seed.py` into the normalized work tables.
- Setup prepares the schema and seeds the catalog idempotently.
- Browse works at GET /items.
- Authenticated users can submit a new work at GET /items with either an external image URL or an uploaded image file.
- Authenticated users can start a review from the new search-first flow at GET /reviews/new:
  - Search for an existing work
  - Reuse an exact/similar match when possible
  - Create a new book entry in a lightweight step when needed
  - Write a linked review with draft/published status and private/followers/public visibility
- Published non-private reviews now emit `feed_event` pointer rows (`target_type=review`, `target_id=<review.id>`).
- On profile pages, owner-only tabs now include:
  - `Drafts`: draft/private reviews, draft/private notes, and private lists for status management and editing
  - `Bookmarks`: private saved-content placeholder, visible only to the profile owner
- Notes are now persisted in `neera_note` with `status` (`draft`, `published`) and `visibility` (`private`, `public`).
- Feed tab now renders from `feed_event` review pointers and links back to the highlighted review on the related item page.
- Public profile tabs only show public content. Private/draft reviews and notes, plus private lists, are excluded from public tabs.
- Item details are available at GET /items/<item_id> with a two-column layout:
  - Left: header, actions, list preview placeholder, reviews stream
  - Right: ratings, your rating placeholder, common work fields plus category metadata, tags/discussion placeholders

## Current Product Priorities (Ignoring Server Setup)

- Expand the create-and-review path beyond books to songs, films, and arts.
- Complete item page data surfaces (related lists, richer ratings, and real discussion references).
- Implement follow graph plus global/following feed modes while preserving pointer-based read-time visibility checks.
- Add heart reactions and post-only comments with owner moderation controls.
- Increase regression coverage for draft/private visibility and stale `feed_event` privacy safety.
