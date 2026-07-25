"""Telemetry dashboard for app-admin."""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, Response, current_app, jsonify, render_template, request

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:
    psycopg = None
    dict_row = None

telemetry_bp = Blueprint("telemetry", __name__)


def _get_pg_conn():
    url = current_app.config.get("TELEMETRY_DATABASE_URL") or os.environ.get("TELEMETRY_DATABASE_URL")
    if not url or psycopg is None:
        return None
    return psycopg.connect(url, row_factory=dict_row)


def _date_clause(field: str, date_from, date_to) -> tuple[str, list[Any]]:
    clauses, params = [], []
    if date_from:
        clauses.append(f"{field} >= %s")
        params.append(date_from)
    if date_to:
        clauses.append(f"{field} <= %s")
        params.append(date_to + " 23:59:59")
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


@telemetry_bp.get("/admin/telemetry")
def dashboard():
    from flask import g
    return render_template(
        "admin_telemetry.html",
        shared_user=getattr(g, "shared_user", None),
        is_admin=getattr(g, "is_admin", False),
    )


@telemetry_bp.get("/admin/telemetry/api/summary")
def api_summary():
    conn = _get_pg_conn()
    if conn is None:
        return jsonify({"error": "Telemetry database not configured"}), 500
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime("%Y-%m-%d")
        seven_days_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d")
        thirty_days_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d")

        total = int(conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"])
        today_events = int(conn.execute("SELECT COUNT(*) AS c FROM events WHERE created_at >= %s", (today,)).fetchone()["c"])
        active_users = int(conn.execute("SELECT COUNT(DISTINCT user_id) AS c FROM events WHERE user_id IS NOT NULL").fetchone()["c"])
        new_users = int(conn.execute(
            "SELECT COUNT(DISTINCT user_id) AS c FROM events WHERE event_type = 'user_first_seen' AND created_at >= %s",
            (seven_days_ago,)
        ).fetchone()["c"])

        avg_session_rows = conn.execute(
            """
            SELECT AVG(duration_ms) AS avg_ms
            FROM (
              SELECT EXTRACT(EPOCH FROM (MAX(created_at) - MIN(created_at))) * 1000 AS duration_ms
              FROM events
              WHERE event_type IN ('page_view', 'page_exit', 'session_start')
              GROUP BY session_id
              HAVING COUNT(*) >= 2
            ) sub
            """
        ).fetchone()
        avg_session_duration = int(avg_session_rows["avg_ms"]) if avg_session_rows and avg_session_rows["avg_ms"] else 0

        top_pages = [
            dict(r) for r in conn.execute(
                """SELECT url, COUNT(*) AS views
                   FROM events
                   WHERE event_type = 'page_view'
                   GROUP BY url
                   ORDER BY views DESC
                   LIMIT 10"""
            ).fetchall()
        ]

        top_features = [
            dict(r) for r in conn.execute(
                """SELECT properties->>'feature_name' AS feature_name, COUNT(*) AS cnt
                   FROM events
                   WHERE event_type = 'feature_click'
                   GROUP BY properties->>'feature_name'
                   ORDER BY cnt DESC
                   LIMIT 10"""
            ).fetchall()
        ]

        daily_rows = conn.execute(
            """SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS events
               FROM events
               WHERE created_at >= %s
               GROUP BY day ORDER BY day ASC""",
            (thirty_days_ago,)
        ).fetchall()
        daily = [dict(r) for r in daily_rows]

        return jsonify({
            "total_events": total,
            "today_events": today_events,
            "active_users": active_users,
            "new_users_7d": new_users,
            "avg_session_duration_ms": avg_session_duration,
            "top_pages": top_pages,
            "top_features": top_features,
            "daily": daily,
        })
    finally:
        conn.close()


@telemetry_bp.get("/admin/telemetry/api/events")
def api_events():
    conn = _get_pg_conn()
    if conn is None:
        return jsonify({"error": "Telemetry database not configured"}), 500
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
        event_type = (request.args.get("event_type") or "").strip()
        user_id = request.args.get("user_id")
        date_from = (request.args.get("date_from") or "").strip()
        date_to = (request.args.get("date_to") or "").strip()

        clauses, params = [], []
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        if user_id:
            clauses.append("user_id = %s")
            params.append(int(user_id))
        where, date_params = _date_clause("substr(created_at, 1, 10)", date_from or None, date_to or None)
        if where.replace(" WHERE ", ""):
            clauses.extend(where.replace(" WHERE ", "").split(" AND "))
        params.extend(date_params)

        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        total = int(conn.execute(f"SELECT COUNT(*) AS c FROM events{where_sql}", params).fetchone()["c"])
        rows = conn.execute(
            f"SELECT * FROM events{where_sql} ORDER BY created_at DESC, id DESC LIMIT %s OFFSET %s",
            params + [limit, offset],
        ).fetchall()
        events = [dict(r) for r in rows]
        for r in events:
            if r.get("properties"):
                try:
                    r["properties_parsed"] = json.loads(r["properties"])
                except Exception:
                    r["properties_parsed"] = None
            if r.get("device_info"):
                try:
                    r["device_info_parsed"] = json.loads(r["device_info"])
                except Exception:
                    r["device_info_parsed"] = None

        return jsonify({"events": events, "total": total, "limit": limit, "offset": offset})
    finally:
        conn.close()


@telemetry_bp.post("/admin/telemetry/api/events/delete")
def api_delete_event():
    conn = _get_pg_conn()
    if conn is None:
        return jsonify({"error": "Telemetry database not configured"}), 500
    try:
        data = request.get_json(silent=True) or {}
        event_id = int(data.get("event_id", 0))
        if not event_id:
            return jsonify({"error": "event_id required"}), 400
        row = conn.execute("SELECT id FROM events WHERE id=%s", (event_id,)).fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404
        conn.execute("DELETE FROM events WHERE id=%s", (event_id,))
        conn.commit()
        return jsonify({"deleted": True})
    finally:
        conn.close()


@telemetry_bp.post("/admin/telemetry/api/events/export")
def api_export_events():
    conn = _get_pg_conn()
    if conn is None:
        return jsonify({"error": "Telemetry database not configured"}), 500
    try:
        date_from = (request.args.get("date_from") or "").strip()
        date_to = (request.args.get("date_to") or "").strip()
        event_type = (request.args.get("event_type") or "").strip()

        clauses, params = [], []
        if event_type:
            clauses.append("event_type = %s")
            params.append(event_type)
        where, date_params = _date_clause("substr(created_at, 1, 10)", date_from or None, date_to or None)
        if where.replace(" WHERE ", ""):
            clauses.extend(where.replace(" WHERE ", "").split(" AND "))
        params.extend(date_params)
        where_sql = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        rows = conn.execute(f"SELECT * FROM events{where_sql} ORDER BY created_at DESC, id DESC", params).fetchall()
        events = [dict(r) for r in rows]

        def _gen():
            header = "id,event_id,event_type,user_id,session_id,url,referrer,properties,device_info,ip_address,created_at\n"
            yield header
            for evt in events:
                line = ",".join([
                    str(evt.get("id", "")),
                    str(evt.get("event_id", "")),
                    str(evt.get("event_type", "")),
                    str(evt.get("user_id", "")),
                    str(evt.get("session_id", "")),
                    '"' + str(evt.get("url", "")).replace('"', '""') + '"',
                    '"' + str(evt.get("referrer", "") or "").replace('"', '""') + '"',
                    '"' + str(evt.get("properties", "") or "").replace('"', '""') + '"',
                    '"' + str(evt.get("device_info", "") or "").replace('"', '""') + '"',
                    str(evt.get("ip_address", "")),
                    str(evt.get("created_at", "")),
                ])
                yield line + "\n"

        return Response(
            _gen(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename=telemetry-{date.today().isoformat()}.csv"},
        )
    finally:
        conn.close()
