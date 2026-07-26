# Telemetry Dashboard Enhancements — Plan

## Goal
Add four analytics features to the existing `/telemetry` surface in `app-landing`:
1. `/telemetry/trends` — time-series chart
2. `/telemetry/devices` — browser / OS / screen breakdown
3. `/telemetry/referrers` — top referrers and entry pages
4. `/telemetry/health-check` — JSON anomaly watch

---

## Scope & Boundaries
- All changes stay inside `app-landing/landing/` (route + query + template),
  plus `app-landing/static/css/main.css`.
- Reuse existing `telemetry_queries.py: _get_pg_conn()`, `_now()`, and the
  `device_info` / `referrer` columns already stored during ingestion.
- No new database tables or migrations.

---

## 1. Time-series trend charts (`/telemetry/trends`)

### Backend (`telemetry_queries.py`)
Add a new function:
```python
def events_time_series(days: int = 30) -> list[dict[str, Any]]:
    ...
    SELECT DATE(created_at) AS day, COUNT(*) AS events,
           COUNT(DISTINCT session_id) AS sessions,
           COUNT(DISTINCT CASE WHEN user_id IS NOT NULL THEN user_id END) AS users
    FROM events
    WHERE created_at >= %s
    GROUP BY day ORDER BY day ASC
```

### Route (`routes.py`)
```python
@main_bp.get("/telemetry/trends")
def telemetry_trends():
    days = int(request.args.get("days", 30))
    ...
    return render_template("telemetry_trends.html", ...)
```

### Template
- `landing/templates/telemetry_trends.html`
- Header with `<input type="date">` from / to (default last 30 days).
- Simple SVG `<polyline>` chart (no chart library dependency):
  - X axis = days, Y axis = events.
  - Compute `max(events)` for scaling.
- Summary row: total events, total sessions, total unique users.

### CSS
- Add `.trend-chart`, `.trend-axis`, `.trend-line` styles to `main.css`.

---

## 2. Browser / device breakdown (`/telemetry/devices`)

### Backend (`telemetry_queries.py`)
```python
def device_breakdown(days: int = 7) -> dict[str, Any]:
    ...
    # Parse device_info JSON fields already stored:
    # - user_agent -> browser family (Chrome/Firefox/Safari/Edge/Other)
    # - screen_width + screen_height -> bucket (Mobile/Tablet/Desktop)
    # Aggregate counts for top 10 each.
```

### Route
```python
@main_bp.get("/telemetry/devices")
def telemetry_devices():
    days = int(request.args.get("days", 7))
    ...
```

### Template
- `landing/templates/telemetry_devices.html`
- Top browsers table (browser, count, %).
- Top OS table — derived from `user_agent` tokens (`Win`, `Mac`, `Linux`, `Android`, `iOS`).
- Screen-size buckets table (Mobile < 768, Tablet 768-1024, Desktop > 1024).

---

## 3. Top referrers / entry pages (`/telemetry/referrers`)

### Backend (`telemetry_queries.py`)
```python
def top_referrers(days: int = 7) -> dict[str, Any]:
    ...
    # Referrers (exclude None/empty/internal)
    SELECT referrer, url, COUNT(*) AS sessions
    FROM events
    WHERE referrer IS NOT NULL AND referrer <> ''
      AND created_at >= %s
      AND referrer NOT LIKE '%31.70.85.89%'
    GROUP BY referrer, url ORDER BY sessions DESC LIMIT 50
```

### Route
```python
@main_bp.get("/telemetry/referrers")
def telemetry_referrers():
    days = int(request.args.get("days", 7))
    ...
```

### Template
- `landing/templates/telemetry_referrers.html`
- Top referrers table (referrer, landing page, sessions).
- Top entry pages table (url, count) for direct / no-referrer traffic.

---

## 4. Lightweight anomaly watch (`/telemetry/health-check`)

### Backend (`telemetry_queries.py`)
```python
def anomaly_check() -> dict[str, Any]:
    ...
    anomalies = []
    # 1. New users last 24h == 0 and total events > 0
    # 2. New users today < 50% of 7d daily average
    # 3. API 5xx rate > 10% over last 24h
    # 4. Worker timeout / out-of-memory signals are not in DB,
    #    so stick to telemetry-derived rules.
    return {"anomalies": anomalies, "checked_at": _now().isoformat()}
```

### Route (`routes.py`)
```python
@main_bp.get("/telemetry/health-check")
def telemetry_health_check():
    from .telemetry_queries import anomaly_check
    return anomaly_check()
```
Returns JSON. No template required.

### Test
Add a test in `tests/test_routes.py` asserting status 200 and JSON shape.

---

## Navigation Updates
- Add links in `telemetry.html` sidebar / reports section to:
  - `/telemetry/trends`
  - `/telemetry/devices`
  - `/telemetry/referrers`
- No changes needed in `admin_telemetry.html` (that stays as the admin-only view).

---

## Testing
- `tests/test_routes.py`: add one test per new route asserting 200 and expected
  JSON keys or HTML markers.
- `tests/test_telemetry.py`: add one test for `anomaly_check()` with empty DB
  returning no anomalies.

---

## Validation
1. Run `FLASK_ENV=testing python3 -m pytest tests/` from `app-landing/`.
2. Start dev server (`app-landing/run.py`) and visit:
   - `http://127.0.0.1:5400/telemetry`
   - `http://127.0.0.1:5400/telemetry/trends?days=14`
   - `http://127.0.0.1:5400/telemetry/devices`
   - `http://127.0.0.1:5400/telemetry/referrers`
   - `http://127.0.0.1:5400/telemetry/health-check`

---

## Rollout / Migration
- Pure Python/Flask + template additions; no DB migration.
- Deploy `app-landing` service restart only.
- Backward compatible: existing `/telemetry` and `/api/telemetry/v1/events`
  unchanged.

---

## Risk / Open Questions
- `device_info` user_agent may be missing for older events; browser/OS buckets
  will show partial data until more events accumulate.
- SVG chart is intentionally dependency-free; if The Nightcraft stack later adds
  a charting lib, swap the SVG block for Chart.js without changing the backend.
