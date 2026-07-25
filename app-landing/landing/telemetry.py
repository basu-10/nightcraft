"""Central telemetry ingestion API."""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict
from typing import Any

from flask import Blueprint, Response, current_app, request
from werkzeug.exceptions import TooManyRequests

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None


telemetry_bp = Blueprint("telemetry", __name__)


def _get_pg_conn():
    url = current_app.config.get("TELEMETRY_DATABASE_URL") or os.environ.get("TELEMETRY_DATABASE_URL")
    if not url or psycopg is None:
        return None
    return psycopg.connect(url, row_factory=dict_row)


_RATE_BUCKETS: dict[str, list[float]] = defaultdict(list)
_SEEN: dict[str, float] = {}
_SEEN_MAX = 4096


def _client_ip() -> str | None:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr


def _rate_limit() -> bool:
    limit = int(current_app.config.get("TELEMETRY_RATE_LIMIT", 1000))
    ip = _client_ip() or "unknown"
    now = time.time()
    window = 60.0
    bucket = _RATE_BUCKETS[ip]
    cutoff = now - window
    while bucket and bucket[0] <= cutoff:
        bucket.pop(0)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _normalize_device(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    ua = (payload.get("user_agent") or "").strip()
    if ua:
        out["user_agent"] = ua[:512]
    if payload.get("screen_width") is not None:
        out["screen_width"] = int(payload["screen_width"])
    if payload.get("screen_height") is not None:
        out["screen_height"] = int(payload["screen_height"])
    if payload.get("timezone") is not None:
        out["timezone"] = str(payload["timezone"])[:64]
    return out


def _normalize_event(payload: dict[str, Any]) -> dict[str, Any] | None:
    allowed_types = {
        "page_view", "page_exit", "scroll_depth", "feature_click",
        "heartbeat", "api_call", "user_first_seen", "session_start",
    }
    event_type = (payload.get("event_type") or "").strip().lower()
    if event_type not in allowed_types:
        return None
    event_id = (payload.get("event_id") or "").strip()
    if not event_id:
        return None
    session_id = (payload.get("session_id") or "").strip()
    if not session_id:
        return None
    url = (payload.get("url") or "").strip()
    if not url:
        return None
    properties = payload.get("properties") or {}
    if not isinstance(properties, dict):
        properties = {}
    referrer = (payload.get("referrer") or "").strip() or None
    user_id = payload.get("user_id")
    if user_id is not None:
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            user_id = None
    device_info = _normalize_device(payload)
    return {
        "event_id": event_id,
        "event_type": event_type,
        "user_id": user_id,
        "session_id": session_id,
        "url": url,
        "referrer": referrer,
        "properties": json.dumps(properties, default=str) if properties else None,
        "device_info": json.dumps(device_info, default=str) if device_info else None,
    }


@telemetry_bp.post("/api/telemetry/v1/events")
def ingest_events():
    try:
        raw = request.get_json(silent=True) or {}
    except Exception:
        raw = {}
    events = raw.get("events") or []
    if not isinstance(events, list):
        events = []

    normalized: list[dict[str, Any]] = []
    rejected = 0
    for item in events:
        if not isinstance(item, dict):
            rejected += 1
            continue
        evt = _normalize_event(item)
        if not evt:
            rejected += 1
            continue
        eid = evt["event_id"]
        now = time.time()
        if eid in _SEEN:
            rejected += 1
            continue
        _SEEN[eid] = now
        if len(_SEEN) > _SEEN_MAX:
            oldest = sorted(_SEEN.items(), key=lambda kv: kv[1])[:_SEEN_MAX // 2]
            _SEEN.clear()
            for k, v in oldest:
                _SEEN[k] = v
        normalized.append(evt)

    if not normalized:
        return {"accepted": 0, "rejected": len(events) + rejected, "errors": ["No valid events"]}, 207

    conn = _get_pg_conn()
    if conn is None:
        return {
            "accepted": len(normalized),
            "rejected": len(events) - len(normalized) + rejected,
            "errors": ["Telemetry database not configured"],
        }, 207

    try:
        ip = _client_ip()
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO events (event_id, event_type, user_id, session_id, url, referrer, properties, device_info, ip_address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                [
                    (
                        evt["event_id"],
                        evt["event_type"],
                        evt["user_id"],
                        evt["session_id"],
                        evt["url"],
                        evt["referrer"],
                        evt["properties"],
                        evt["device_info"],
                        ip,
                    )
                    for evt in normalized
                ],
            )
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return {
            "accepted": 0,
            "rejected": len(events),
            "errors": ["Database error"],
        }, 207
    finally:
        conn.close()

    return {
        "accepted": len(normalized),
        "rejected": len(events) - len(normalized) + rejected,
        "errors": [],
    }, 207


@telemetry_bp.before_request
def _check_rate_limit():
    if not _rate_limit():
        raise TooManyRequests("Rate limit exceeded")
