from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import current_user
from sqlalchemy import text

from ..auth.utils import admin_required
from ..extensions import db
from ..models import AgentRun, User
from ..core.activity_log import get_logger


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _to_user_dict(row: User) -> dict:
    return {
        "id": row.id,
        "email": row.email,
        "is_admin": row.is_admin,
        "active": row.active,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@admin_bp.get("/users")
@admin_required
def list_users():
    rows = User.query.order_by(User.created_at.asc()).all()
    return jsonify([_to_user_dict(r) for r in rows]), 200


@admin_bp.post("/users")
@admin_required
def create_user():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        return jsonify({"error": "email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "Email already registered."}), 409
    user = User(email=email, is_admin=bool(payload.get("is_admin", False)))
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(_to_user_dict(user)), 201


@admin_bp.patch("/users/<user_id>")
@admin_required
def update_user(user_id: str):
    row = User.query.get(user_id)
    if not row:
        return jsonify({"error": "User not found."}), 404
    payload = request.get_json(silent=True) or {}
    if "is_admin" in payload:
        # Prevent self-demotion
        if row.id == current_user.id and not payload["is_admin"]:
            return jsonify({"error": "Cannot remove admin from your own account."}), 400
        row.is_admin = bool(payload["is_admin"])
    if "active" in payload:
        row.active = bool(payload["active"])
    db.session.commit()
    return jsonify(_to_user_dict(row)), 200


@admin_bp.post("/users/<user_id>/password")
@admin_required
def reset_password(user_id: str):
    row = User.query.get(user_id)
    if not row:
        return jsonify({"error": "User not found."}), 404
    payload = request.get_json(silent=True) or {}
    new_password = payload.get("new_password") or ""
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400
    row.set_password(new_password)
    db.session.commit()
    return jsonify({"ok": True}), 200


@admin_bp.delete("/users/<user_id>")
@admin_required
def delete_user(user_id: str):
    if user_id == current_user.id:
        return jsonify({"error": "Cannot delete your own account."}), 400
    row = User.query.get(user_id)
    if not row:
        return jsonify({"error": "User not found."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@admin_bp.get("/stats")
@admin_required
def admin_stats():
    user_count = User.query.count()
    run_count = AgentRun.query.count()
    today = datetime.utcnow().date()
    runs_today = AgentRun.query.filter(
        db.func.date(AgentRun.created_at) == today.isoformat()
    ).count()
    return jsonify({
        "user_count": user_count,
        "run_count": run_count,
        "runs_today": runs_today,
    }), 200


@admin_bp.get("/activity_logs")
@admin_required
def admin_activity_logs():
    """Query activity logs from PostgreSQL.

    Query parameters
    ----------------
    user_id     — filter by exact user_id
    session_id  — filter by exact session_id
    run_id      — filter by exact run_id
    event_type  — filter by event type (e.g. llm_call, tool_retry)
    since       — ISO timestamp lower bound (inclusive)
    until       — ISO timestamp upper bound (inclusive)
    limit       — max rows to return (default 100, max 1000)
    offset      — pagination offset (default 0)
    """
    _logger = get_logger()
    if _logger is None:
        return jsonify({"error": "activity logger not initialised"}), 503

    uid        = request.args.get("user_id", "").strip()
    sid        = request.args.get("session_id", "").strip()
    rid        = request.args.get("run_id", "").strip()
    evt        = request.args.get("event_type", "").strip()
    since      = request.args.get("since", "").strip()
    until      = request.args.get("until", "").strip()
    try:
        limit  = min(int(request.args.get("limit", 100)), 1000)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers"}), 400

    clauses: list[str] = []
    params: dict[str, object] = {}

    if uid:
        clauses.append("user_id = :uid")
        params["uid"] = uid
    if sid:
        clauses.append("session_id = :sid")
        params["sid"] = sid
    if rid:
        clauses.append("run_id = :rid")
        params["rid"] = rid
    if evt:
        clauses.append("event_type = :evt")
        params["evt"] = evt
    if since:
        clauses.append("ts >= :since")
        params["since"] = since
    if until:
        clauses.append("ts <= :until")
        params["until"] = until

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    try:
        count_sql = text(f"SELECT COUNT(*) AS total FROM activity_log {where}")
        rows_sql = text(
            f"""
            SELECT id, ts, event_type, user_id, session_id, run_id,
                   data_json, duration_ms
            FROM activity_log
            {where}
            ORDER BY ts DESC
            LIMIT :limit OFFSET :offset
            """
        )

        with _logger.engine.connect() as con:
            total = con.execute(count_sql, params).scalar_one()
            rows = con.execute(rows_sql, {**params, "limit": limit, "offset": offset}).mappings().all()
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500

    return jsonify({
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [
            {
                "id":          r["id"],
                "ts":          r["ts"].isoformat() if hasattr(r["ts"], "isoformat") else str(r["ts"]),
                "event_type":  r["event_type"],
                "user_id":     r["user_id"],
                "session_id":  r["session_id"],
                "run_id":      r["run_id"],
                "data":        r["data_json"],
                "duration_ms": r["duration_ms"],
            }
            for r in rows
        ],
    }), 200
