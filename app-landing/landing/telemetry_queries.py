"""Telemetry read-model queries for the admin dashboard."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover
    psycopg = None
    dict_row = None


def _get_pg_conn():
    url = os.environ.get("TELEMETRY_DATABASE_URL") or os.environ.get("TELEMETRY_DATABASE_URL", "")
    if not url or psycopg is None:
        return None
    return psycopg.connect(url, row_factory=dict_row)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _is_within(dt: datetime | None, start: datetime) -> bool:
    if dt is None:
        return False
    return dt >= start


def overview() -> dict[str, Any]:
    conn = _get_pg_conn()
    if conn is None:
        return {"error": "Telemetry database not configured"}

    now = _now()
    ranges = {
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }

    result: dict[str, Any] = {"ranges": {}, "totals": {}}
    try:
        with conn.cursor() as cur:
            for label, start in ranges.items():
                cur.execute(
                    "SELECT COUNT(*) AS total FROM events WHERE created_at >= %s",
                    (start,),
                )
                total = cur.fetchone()["total"]

                cur.execute(
                    "SELECT COUNT(DISTINCT user_id) AS users FROM events WHERE user_id IS NOT NULL AND created_at >= %s",
                    (start,),
                )
                active_users = cur.fetchone()["users"]

                cur.execute(
                    "SELECT COUNT(*) AS total FROM events WHERE event_type = 'user_first_seen' AND created_at >= %s",
                    (start,),
                )
                new_users = cur.fetchone()["total"]

                cur.execute(
                    "SELECT AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER w))) AS avg_sec FROM events WINDOW w AS (PARTITION BY session_id ORDER BY created_at) WHERE event_type = 'page_exit' AND created_at >= %s",
                    (start,),
                )
                avg_duration_row = cur.fetchone()
                avg_duration = avg_duration_row["avg_sec"] if avg_duration_row and avg_duration_row.get("avg_sec") is not None else None

                result["ranges"][label] = {
                    "events": total,
                    "active_users": active_users,
                    "new_users": new_users,
                    "avg_session_seconds": round(avg_duration, 1) if avg_duration is not None else None,
                }

            cur.execute(
                "SELECT COUNT(DISTINCT session_id) AS sessions, ROUND(AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER w))), 1) AS avg_sec FROM events WINDOW w AS (PARTITION BY session_id ORDER BY created_at) WHERE event_type = 'page_exit'"
            )
            session_row = cur.fetchone()
            result["totals"]["sessions"] = session_row["sessions"] if session_row else 0
            result["totals"]["avg_session_seconds"] = session_row["avg_sec"] if session_row and session_row.get("avg_sec") is not None else None
    except Exception:
        pass
    finally:
        conn.close()

    return result


def new_users_timeline(days: int = 30) -> list[dict[str, Any]]:
    conn = _get_pg_conn()
    if conn is None:
        return []

    start = _now() - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DATE(created_at) AS day, COUNT(*) AS count
                FROM events
                WHERE event_type = 'user_first_seen' AND created_at >= %s
                GROUP BY day ORDER BY day ASC
                """,
                (start,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    finally:
        conn.close()
    return rows


def page_performance(days: int = 7) -> dict[str, Any]:
    conn = _get_pg_conn()
    if conn is None:
        return {"pages": [], "avg_duration_seconds": None, "bounce_rate": None}

    start = _now() - timedelta(days=days)
    pages: list[dict[str, Any]] = []
    avg_duration = None
    bounce_rate = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH page_views AS (
                    SELECT session_id, url, COUNT(*) AS views
                    FROM events
                    WHERE event_type = 'page_view' AND created_at >= %s
                    GROUP BY session_id, url
                )
                SELECT url,
                       COUNT(*) AS sessions,
                       ROUND(100.0 * SUM(CASE WHEN views = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS bounce_pct
                FROM page_views
                GROUP BY url
                ORDER BY sessions DESC
                LIMIT 50
                """,
                (start,),
            )
            pages = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                WITH session_pages AS (
                    SELECT session_id, COUNT(DISTINCT url) AS page_count
                    FROM events
                    WHERE event_type = 'page_view' AND created_at >= %s
                    GROUP BY session_id
                )
                SELECT ROUND(100.0 * SUM(CASE WHEN page_count = 1 THEN 1 ELSE 0 END) / COUNT(*), 1) AS bounce_pct
                FROM session_pages
                """,
                (start,),
            )
            bounce_row = cur.fetchone()
            bounce_rate = bounce_row["bounce_pct"] if bounce_row else None

            cur.execute(
                """
                SELECT ROUND(AVG(EXTRACT(EPOCH FROM (created_at - LAG(created_at) OVER w))), 1) AS avg_sec
                FROM events WINDOW w AS (PARTITION BY session_id ORDER BY created_at)
                WHERE event_type = 'page_exit' AND created_at >= %s
                """,
                (start,),
            )
            avg_row = cur.fetchone()
            avg_duration = avg_row["avg_sec"] if avg_row and avg_row.get("avg_sec") is not None else None
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "pages": pages,
        "avg_duration_seconds": avg_duration,
        "bounce_rate": bounce_rate,
    }


def feature_usage(days: int = 7) -> list[dict[str, Any]]:
    conn = _get_pg_conn()
    if conn is None:
        return []

    start = _now() - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT (properties->>'feature_name') AS feature_name, COUNT(*) AS clicks
                FROM events
                WHERE event_type = 'feature_click' AND created_at >= %s
                GROUP BY feature_name ORDER BY clicks DESC LIMIT 20
                """,
                (start,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    finally:
        conn.close()
    return rows


def scroll_depth_distribution(days: int = 7) -> list[dict[str, Any]]:
    conn = _get_pg_conn()
    if conn is None:
        return []

    start = _now() - timedelta(days=days)
    rows: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT url,
                       ROUND(100.0 * SUM(CASE WHEN (properties->>'depth_pct')::int >= 100 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_100,
                       ROUND(100.0 * SUM(CASE WHEN (properties->>'depth_pct')::int >= 75 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_75,
                       ROUND(100.0 * SUM(CASE WHEN (properties->>'depth_pct')::int >= 50 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_50,
                       ROUND(100.0 * SUM(CASE WHEN (properties->>'depth_pct')::int >= 25 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_25,
                       COUNT(*) AS events
                FROM events
                WHERE event_type = 'scroll_depth' AND created_at >= %s
                GROUP BY url ORDER BY events DESC LIMIT 20
                """,
                (start,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    finally:
        conn.close()
    return rows


def api_health(days: int = 7) -> dict[str, Any]:
    conn = _get_pg_conn()
    if conn is None:
        return {"calls": [], "success_rate": None, "p95_ms": None}

    start = _now() - timedelta(days=days)
    calls: list[dict[str, Any]] = []
    success_rate = None
    p95_ms = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT (properties->>'status')::int AS status, COUNT(*) AS count
                FROM events
                WHERE event_type = 'api_call' AND created_at >= %s
                GROUP BY status ORDER BY count DESC
                """,
                (start,),
            )
            status_rows = [dict(r) for r in cur.fetchall()]
            total = sum(r["count"] for r in status_rows)
            success = sum(r["count"] for r in status_rows if r["status"] and 200 <= r["status"] < 300)
            success_rate = round(100.0 * success / total, 1) if total else None

            cur.execute(
                """
                SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (properties->>'duration_ms')::numeric) AS p95
                FROM events
                WHERE event_type = 'api_call' AND created_at >= %s
                """,
                (start,),
            )
            p95_row = cur.fetchone()
            p95_ms = round(p95_row["p95"], 1) if p95_row and p95_row.get("p95") is not None else None

            cur.execute(
                """
                SELECT (properties->>'url') AS url, COUNT(*) AS count,
                       ROUND(AVG((properties->>'duration_ms')::numeric), 1) AS avg_ms,
                       ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (properties->>'duration_ms')::numeric), 1) AS p95_ms
                FROM events
                WHERE event_type = 'api_call' AND created_at >= %s
                GROUP BY url ORDER BY count DESC LIMIT 20
                """,
                (start,),
            )
            calls = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    finally:
        conn.close()

    return {
        "calls": calls,
        "success_rate": success_rate,
        "p95_ms": p95_ms,
        "status_breakdown": status_rows if 'status_rows' in dir() else [],
    }


def events_list(filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    conn = _get_pg_conn()
    if conn is None:
        return {"events": [], "total": 0}

    filters = filters or {}
    where: list[str] = []
    params: list[Any] = []

    if filters.get("event_type"):
        where.append("event_type = %s")
        params.append(filters["event_type"])
    if filters.get("user_id"):
        where.append("user_id = %s")
        params.append(int(filters["user_id"]))
    if filters.get("session_id"):
        where.append("session_id = %s")
        params.append(filters["session_id"])
    if filters.get("date_from"):
        where.append("created_at >= %s")
        params.append(_utc(filters["date_from"]))
    if filters.get("date_to"):
        where.append("created_at <= %s")
        params.append(_utc(filters["date_to"]))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    rows: list[dict[str, Any]] = []
    total = 0
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS total FROM events {where_sql}",
                params,
            )
            total = cur.fetchone()["total"]

            cur.execute(
                f"""
                SELECT id, event_id, event_type, user_id, session_id, url, referrer,
                       properties, device_info, ip_address, created_at
                FROM events {where_sql}
                ORDER BY created_at DESC LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            rows = [dict(r) for r in cur.fetchall()]
    except Exception:
        pass
    finally:
        conn.close()

    return {"events": rows, "total": total}


def delete_event(event_id: str) -> bool:
    conn = _get_pg_conn()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM events WHERE event_id = %s", (event_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        conn.close()
