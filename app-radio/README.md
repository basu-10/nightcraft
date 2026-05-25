# DevRadio MVP

DevRadio is a 24/7 developer-news radio platform built with Flask, Jinja, HTMX, and Alpine.

## Stack

- Flask + Jinja templates
- HTMX + Alpine.js for lightweight interactivity
- PostgreSQL database
- Role-based access (admin/listener)
- OpenRouter integration for summary generation and TTS

## Auth Architecture (Migration In Progress)

- `AUTH_MODE=local` is the default and current runtime mode.
- Local login now uses `LocalCredential` for password/role and `UserProfile` for app-level profile data.
- Saved stories are linked to `UserProfile` rows, not credential rows.
- In local mode, missing `UserProfile` rows are auto-created on first authenticated listener access.
- In SSO mode, `/auth/callback` now upserts `UserProfile` and the session mirrors that persisted profile.
- In SSO mode, admin access is derived from the `roles` claim. `is_admin` is treated as a derived compatibility signal when older tokens omit roles.
- Templates should use `app_user` (injected from `get_current_user()`) for auth-aware UI checks instead of relying on flask-login `current_user` attributes.
- Route protection for app blueprints uses `auth_required` from `devradio.guards` (mode-agnostic), while `local_auth.py` keeps flask-login-specific checks for local login/logout handling.
- A mode-based auth adapter package lives under `devradio/auth/` (`local_auth.py`, `sso_auth.py`, `current_user.py`) so SSO can be added without changing product routes.

### SSO Quick Start (In Progress)

When running against the new `service-auth` app directly in development:

```env
FLASK_AUTH_MODE=sso
FLASK_AUTH_SERVICE_URL=http://localhost:5100
FLASK_AUTHLIB_CLIENT_ID=radio-app
FLASK_AUTHLIB_CLIENT_SECRET=dev-secret
```

For standalone mode, keep `AUTH_MODE=local`.

The expected auth-service claim contract for SSO is: `sub`, `preferred_username`, `email`, `roles`, optional derived `is_admin`, and optional `timezone_name`.

## Features in this MVP

- Separate listener and admin login flows
- Listener self-signup (listener role only)
- Admin 3-stage workflow:
  - Stage 1 Intake: manual upload/paste + staged review
  - Stage 2 Editorial: frozen intake data + auto-generation + browser-TTS preview prep
  - Stage 3 Queue Board: all 3 channel queues with totals, current item, remaining counts, and cross-channel "currently playing now" panel
- Admin Automated workflow page:
  - 3-column source allocation board (map tested sources to channels)
  - Hourly automated ingestion from mapped sources only
  - Configurable per-feed fetch limit in Hourly Automation (`0` = fetch full feed)
  - Queue only new URLs and only when full source-article fetch succeeds
- Breaking-news playback insertion:
  - When new segments are queued while a channel is already looping, current story continues first
  - Newly queued stories are inserted right after current story for one temporary cycle
  - Remaining older stories resume after inserted stories
  - After that temporary cycle completes, playback order returns to canonical recency order
  - Listener and admin UIs mark inserted rows with `Breaking Now`
- Stage transitions: Stage 1 approve -> Stage 2, Stage 2 queue -> Stage 3
- Stage 1 moderation actions include both soft reject and permanent delete
- Stage 1 source-group moderation supports reject-all and delete-all for each grouped source
- Stage 1 includes a Rejected Items section with permanent delete controls
- Channel pages showing only current and past stories for today
- Player loop model with timer-based clip offset (no background looping worker)
- Browser-based TTS playback in listener player via Web Speech API (no server audio required)
- Bookmark and share story actions (live player + article detail views)
- Ingestion from curated legal/public RSS sources
- Optional full-article extraction by visiting each source link from RSS items
- Expanded default free/open-source feed set for AI, web dev, and game dev channels
- OpenRouter chat-based summary/script generation
- OpenRouter TTS generation pipeline using `openai/gpt-4o-mini-tts-2025-12-15`
- Encrypted-at-rest API key storage in DB
- Cron-friendly CLI commands for PythonAnywhere free tier

## Default Accounts

These are seeded by setup command (idempotent):

- Admin: `admin` / `admin123`
- Listener: `testuser` / `test123`

## Quick Start

For standalone local development (single app download), use the one-command PowerShell script:

```powershell
.\dev-start.ps1
```

For SSO mode against local `service-auth`:

```powershell
.\dev-start.ps1 -AuthMode sso -AuthServiceUrl http://127.0.0.1:5100 -AuthClientId radio-app -AuthClientSecret dev-secret
```

The script will:

- Create `.venv` if missing
- Install `requirements.txt`
- Use `FLASK_SQLALCHEMY_DATABASE_URI` with PostgreSQL
- Run setup (idempotent table/account/feed bootstrap)
- Start the app

1. Create and activate venv.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

1. Optional: copy environment template:

```powershell
copy .env.example .env
```

1. Initialize app data and defaults:

```powershell
flask --app devradio setup
```

1. Start server:

```powershell
flask --app devradio run
```

Open <http://127.0.0.1:5000/>.

## CLI Commands

- `flask --app devradio setup`
  - Creates DB tables
  - Seeds channels, feeds, and default accounts
  - Safe to re-run to add newly introduced default feed sources

- `flask --app devradio ingest-feeds`
  - Pulls items from configured RSS feeds into staging queue
  - Attempts to fetch full source-article text from each item's source URL (when available)

- `flask --app devradio build-audio`
  - Builds TTS audio for approved queued segments

- `flask --app devradio advance-radio`
  - Marks segment states based on current time

- `flask --app devradio automated-run`
  - Runs automated mapped-source ingestion immediately (same logic as hourly worker)
  - Prints run id, fatal error status, and saved log file path

- `flask --app devradio migrate-automation-log-timezone`
  - Converts historical automation log timestamps to app timezone (`Asia/Kolkata`, UTC+5:30)
  - Rewrites `run_*.json`, `latest.json`, and `runs.jsonl` timestamps in-place

## OpenRouter API Key Storage

1. Log in as admin.
2. Open Admin Settings page.
3. Save OpenRouter API key.

Admin Settings also includes a destructive reset action that permanently clears article staging, queue segments, and saved-story links while preserving user login accounts.

The key is encrypted before storing in DB.

## Source Fetching Behavior

- Stage 1 ingestion begins from RSS/Atom feeds via `feedparser`.
- Duplicate detection is URL-based across stored articles; soft-rejected rows still exist, while permanently deleted rows can be ingested again.
- For each new feed entry, DevRadio can visit the source URL and attempt to extract full article text.
- Extracted full text is stored in `article.source_full_article` and shown as a badge in Stage 1/2.
- Stage 2 `From Source (pre-filled)` now includes `Full article (from source)`.

Automated page source mapping is intentionally restricted to validated source keys:

- `google_deepmind_blog`
- `google_for_developers`
- `hugging_face_blog`
- `nvidia_developer_blog`
- `the_linux_foundation_blog`
- `together_ai_blog`
- `github_changelog`
- `docker_blog`
- `jetbrains_blog`
- `mdn_blog`
- `vercel_blog`
- `web_dev`
- `gamesindustry_biz`
- `itch_io_blog`
- `unity_blog`

Automated ingestion rules:

- Runs hourly in-app by default (`AUTOMATED_INGEST_INTERVAL_SECONDS=3600`)
- Processes only mapped sources from the Automated page
- Uses the saved Hourly Automation feed cap (`automated_feed_fetch_limit`), where `0` means no per-feed cap
- Tracks `source_feed.automated_last_published_at` so each feed resumes from its latest published timestamp instead of always rescanning only the raw top `N` items
- Deduplicates strictly on source URL (`article.source_url`)
- Skips queueing when full source article fetch fails
- Keeps current queue intact if no new stories are found, so listener playback continues in repeat-all loop behavior
- Uses database-level uniqueness on `article.source_url` to prevent duplicate insert races across overlapping runs

## Automated Run Logs And Retry

Every automated run now persists structured log artifacts under:

- `instance/automation_logs/run_<timestamp>.json`
- `instance/automation_logs/latest.json`
- `instance/automation_logs/runs.jsonl`
- `instance/automation_logs/breaking_playback.jsonl`

Automation log timestamps are stored and shown in `Asia/Kolkata` (UTC+5:30 / IST).

Retention is automatically pruned:

- Keep only the newest `AUTOMATED_LOG_MAX_RUN_FILES` `run_*.json` files (default: `500`)
- Keep only the newest `AUTOMATED_LOG_MAX_JSONL_LINES` lines in `runs.jsonl` (default: `5000`)

Each run log contains:

- Run timing (IST) and summary counters
- Per-run events (queued article events, lifecycle notes)
- Failure records with reason/source/url/status/error
- Retry status updates for retried failures
- Breaking reorder updates with channel id, injected segment ids, and selected anchor segment

Admin Automated page now includes:

- Recent runs table with status and open-log action
- Latest run failure list for quick debugging
- Retry actions for selected failures or all retryable failures

The source fetch flow is designed to be polite and reduce rate-limit risk:

- Per-host pacing (`SOURCE_FETCH_MIN_DELAY_SECONDS` + `SOURCE_FETCH_JITTER_SECONDS`)
- Retry with backoff (`SOURCE_FETCH_MAX_RETRIES`, `SOURCE_FETCH_RETRY_BACKOFF_SECONDS`)
- Timeout limits (`SOURCE_FETCH_TIMEOUT_SECONDS`)
- Optional robots.txt checks (`SOURCE_FETCH_RESPECT_ROBOTS`)
- Transparent user agent (`SOURCE_FETCH_USER_AGENT`)

Relevant config keys (set via environment or app config):

- `SOURCE_FETCH_ENABLED`
- `SOURCE_FETCH_USER_AGENT`
- `SOURCE_FETCH_TIMEOUT_SECONDS`
- `SOURCE_FETCH_MIN_CHARS`
- `SOURCE_FETCH_MAX_CHARS`
- `SOURCE_FETCH_MIN_DELAY_SECONDS`
- `SOURCE_FETCH_JITTER_SECONDS`
- `SOURCE_FETCH_MAX_RETRIES`
- `SOURCE_FETCH_RETRY_BACKOFF_SECONDS`
- `SOURCE_FETCH_RESPECT_ROBOTS`

## PythonAnywhere Notes

- Compatible with free tier constraints (no Redis/Celery).
- Use scheduled tasks to run CLI commands periodically:
  - `ingest-feeds`
  - `build-audio`
  - `advance-radio`

## Tests

Run:

```powershell
pytest
```

Auth guard regression coverage is in [tests/test_auth_required.py](tests/test_auth_required.py), including:

- local mode unauthenticated redirect
- local mode authenticated access
- sso mode unauthenticated redirect
- sso mode authenticated session+profile access

## RSS Reachability Harness

Use this standalone harness to verify one RSS item per default source feed and test whether full article text can be fetched from each selected source link.

```powershell
python tests/rss_article_fetch_harness.py
```

The harness is intentionally isolated from Flask app state and DB writes. It logs detailed run activity and writes structured artifacts under `tests/harness_output/rss_harness_<timestamp>/`:

- `harness_run.log` (step-by-step run logs)
- `results.json` (summary + all source results)
- `results.jsonl` (one JSON record per source)
- `article_text/*.txt` (full extracted article text for each successful source fetch)

Useful options:

```powershell
python tests/rss_article_fetch_harness.py --max-sources 15 --rss-min-delay 2.5 --article-min-delay 3.0 --respect-robots
```
