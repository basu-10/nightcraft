# Global Telemetry Plan

## 1. Goal
Add lightweight, centralized telemetry across all Nightcraft apps to track:
- New user acquisition
- Time spent per page/session
- Feature/button interactions
- Scroll depth per page

**Constraint:** Zero perceptible impact on page responsiveness or bundle size.

---

## 2. Architecture Decision: Centralized Shared Layer
All telemetry logic lives in **one backend service + one frontend SDK file**. Each app only needs a **2-line template change** — no per-app Python logic, no copied code.

| Component | Location | Purpose |
|---|---|---|
| `telemetry_db` | Shared PostgreSQL | Single event store for all apps |
| Telemetry API | `app-landing` at `/api/telemetry/v1/events` | Central HTTP ingestion point |
| Telemetry SDK | `app-landing/static/telemetry-sdk.js` | One shared JS file, auto-initializes |
| Admin Dashboard | `app-admin` at `/admin/telemetry` | Unified view across all apps |

---

## 3. Database Schema
New database: `telemetry_db`

```sql
CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    event_id        TEXT NOT NULL UNIQUE,          -- UUIDv7, client-generated for dedup
    event_type      TEXT NOT NULL,                 -- page_view, page_exit, scroll_depth, feature_click, heartbeat, api_call, user_first_seen, session_start
    user_id         BIGINT,                        -- NULL for guests
    session_id      TEXT NOT NULL,                 -- browser session ID (persists across apps)
    url             TEXT NOT NULL,                 -- full page URL
    referrer        TEXT,
    properties      JSONB,                         -- event-specific data (duration, depth_pct, feature_name, status, etc.)
    device_info     JSONB,                         -- sent once per session: ua, screen, timezone
    ip_address      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_events_type_time ON events (event_type, created_at DESC);
CREATE INDEX idx_events_user_time ON events (user_id, created_at DESC) WHERE user_id IS NOT NULL;
CREATE INDEX idx_events_session ON events (session_id, created_at);
```

**Retention:** Events older than 90 days moved to cold storage or deleted via scheduled job.

---

## 4. Backend: Central Telemetry API
Add to `app-landing` (root app, already serves static assets):

**Endpoint:** `POST /api/telemetry/v1/events`
- Accepts batched JSON: `{ "events": [ ... ] }`
- Validates `event_id` uniqueness (skip duplicates)
- Bulk inserts with `executemany` / `COPY`
- Returns `207 Multi-Status` with per-event accept/reject counts
- Rate limits by IP: 1000 events/minute
- Auth: open to all apps (internal network + CORS for same-origin policy under nginx)

**Why `app-landing`:** It is mounted at `/` and already serves the shared static JS. Hosting the API here avoids a new service dependency.

---

## 5. Frontend SDK (`telemetry-sdk.js`)
Single vanilla JS file (~3KB gzipped). No dependencies. Auto-initializes.

### 5.1 Initialization
```html
<script>
  window.__TELEMETRY__ = {
    endpoint: "/api/telemetry/v1/events",
    userId: {{ user.id if user else 'null' }},
    sessionId: "{{ session_id or generate_uuid() }}"
  };
</script>
<script src="/static/telemetry-sdk.js"></script>
```

### 5.2 Tracked Events

| Event | When Fired | Key Properties |
|---|---|---|
| `session_start` | First page load or after 30min inactivity | `device_info` (UA, screen, timezone) |
| `page_view` | Page load + SPA navigation | `url`, `referrer`, `title` |
| `page_exit` | `visibilitychange` to hidden / `beforeunload` | `url`, `duration_ms` |
| `heartbeat` | Every 30s while tab is active | `url`, `session_seconds` |
| `scroll_depth` | At 25%, 50%, 75%, 100% per page | `url`, `depth_pct` |
| `feature_click` | Click on `[data-track]` elements | `url`, `feature_name`, `element_text` |
| `api_call` | fetch/XHR completed | `url`, `method`, `status`, `duration_ms` |
| `user_first_seen` | First `page_view` where `user_id` transitions from null to non-null | `user_id`, `url` |

### 5.3 Performance Guarantees
- **`navigator.sendBeacon`** for all sends — async, non-blocking, survives page unload
- **Batching:** Queue events in memory, flush every 5s or when batch hits 20 events
- **Throttling:** scroll events max once per 500ms; depth milestones only
- **`requestIdleCallback`** for non-critical sends (device_info, heartbeat)
- **No layout thrashing:** scroll depth uses `requestAnimationFrame`-throttled reads
- **Zero external dependencies:** pure DOM APIs
- **Graceful degradation:** if SDK fails to load, nothing breaks

---

## 6. Per-App Integration (Minimal)
Each app needs only a **2-line change** to its base Jinja template:

```html
{% if not config.get('TELEMETRY_DISABLED') %}
<script>
  window.__TELEMETRY__ = {
    endpoint: "{{ config.TELEMETRY_ENDPOINT }}",
    userId: {{ current_user.id if current_user else 'null' }},
    sessionId: "{{ session.get('telemetry_session_id') or (session['telemetry_session_id'] = generate_uuid()) }}"
  };
</script>
<script src="{{ url_for('static', filename='telemetry-sdk.js') }}"></script>
{% endif %}
```

**How this works across apps:**
- `TELEMETRY_ENDPOINT` is an env var defaulting to `http://localhost/api/telemetry/v1/events` (resolved by nginx to `app-landing`)
- `current_user` pattern already exists in every app's auth adapter
- `generate_uuid()` is stdlib
- The static JS file can be symlinked or copied into each app's `static/` folder, OR served from a shared static prefix

**No Python code changes required** in any app for basic page/scroll/click tracking.

---

## 7. Auth Service Integration (Optional, Recommended)
To capture `auth_register` / `auth_login` events **even without JS** and to attribute the very first page view after login:

Modify `service-auth` to emit a `user_first_seen` and `session_resumed` event to the telemetry API after successful login/registration. This covers all apps because `service-auth` is the single OAuth2 provider.

If modifying `service-auth` is out of scope, the JS SDK handles this client-side on the first post-login page view.

---

## 8. Admin Dashboard (`app-admin`)
New section at `/admin/telemetry` with:

### 8.1 Overview Cards
- Total events (24h / 7d / 30d)
- Active users (distinct)
- New users (first `user_first_seen` event)
- Avg session duration
- Avg scroll depth per page

### 8.2 Reports
- **New Users:** timeline of `user_first_seen` events, by app
- **Page Performance:** avg time on page, bounce rate (single-page sessions), top pages
- **Feature Usage:** top `feature_click` events grouped by `feature_name`
- **Scroll Depth:** distribution of `scroll_depth` per URL
- **API Health:** `api_call` success rate, latency percentiles

### 8.3 Actions
- Filter by user, app, date range, event type
- Export CSV/JSON
- Delete events (GDPR compliance)

### 8.4 Implementation Notes
- Use materialized views refreshed every 5 minutes for summary stats
- Raw event queries paginated, indexed by `created_at DESC`
- Heavy aggregations run as async Celery/RQ tasks or via `refresh materialized view`

---

## 9. Privacy & Performance Safeguards

### Privacy
- **No note contents, secrets, or form field values** are captured
- `feature_click` records only the `data-track` attribute value and element text (not input values)
- `api_call` records URL path + method + status, not request/response bodies
- IP addresses truncated to /24 or /64 (or dropped after 30 days)
- User-agent replaced with parsed `device_info` (OS, browser family) after ingestion
- Events can be deleted by `user_id` for GDPR

### Performance
- **Client:** All sends are non-blocking beacons. Max 20 events per batch. Max 500ms added to critical path.
- **Server:** Bulk insert via COPY. API response target < 50ms p95. Events are fire-and-forget from the app's perspective.
- **Database:** Partition `events` by month, or use TimescaleDB if available. Index only what the dashboard queries.
- **Static asset:** `telemetry-sdk.js` is cached indefinitely (`Cache-Control: public, max-age=31536000, immutable`) with content hash in filename.

---

## 10. Rollout Plan

1. **Provision `telemetry_db`** and run schema migration
2. **Add telemetry API routes** to `app-landing`
3. **Build `telemetry-sdk.js`** with unit tests for batching, dedup, and beacon fallback
4. **Update `app-landing` base template** with the 2-line snippet
5. **Update `app-admin`** with telemetry dashboard
6. **Optional:** Patch `service-auth` to emit auth events
7. **Optional:** Add `data-track` attributes to high-value buttons in `app-note` and `app-landing`
8. **Deploy to staging**, verify: network tab shows beacon fires, dashboard shows data, no console errors
9. **Roll out to remaining apps** by updating their base templates (one PR per app or a monorepo-wide search-replace)
10. **Monitor:** dashboard load times, DB table growth, client-side CPU/memory

---

## 11. Open Questions / Out of Scope
- Should we use an existing analytics tool (PostHog, Plausible) instead of building custom? → Out of scope unless requested
- Should we track WebSocket / SSE events? → Future iteration
- Should we track offline PWA usage with background sync? → Future iteration
- Should events be correlated across apps via a shared `user_id` from `service-auth`? → Yes, `user_id` is passed in the template context from the local session, which is bridged from `service-auth` in SSO mode

---

## 12. Implementation Order
1. `telemetry_db` + schema
2. `app-landing` telemetry API + `telemetry-sdk.js`
3. `app-admin` dashboard (MVP: new users + page views)
4. Template rollout (landing first, then note, then rest)
5. Auth service integration
6. Advanced features: scroll depth, feature clicks, API call tracking
