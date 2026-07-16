"""API blueprint: run lifecycle, event polling, drag-drop ingest, heartbeat."""

from __future__ import annotations

import os
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request

from .agent.executor import run_workflow
from .agent.events import get_events
from .agent.planner import plan_goal
from .agent import executor as executor_module
from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required
from .ingest import ingest_bytes
from .keepalive import start_run_keepalive, stop_run_keepalive
from .models import AgentRun, Asset, ChatSession, Message

bp = Blueprint("api", __name__, url_prefix="/alfred/api")


def _require_user():
    user = get_current_user()
    if not user.is_authenticated:
        return None
    return user


@bp.post("/runs")
@auth_required
def start_run():
    user = _require_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    goal = (data.get("goal") or "").strip()
    if not goal:
        return jsonify({"error": "goal is required"}), 400

    session_id = (data.get("session_id") or "").strip()
    if not session_id:
        session = ChatSession(session_id=uuid.uuid4().hex, user_id=user.user_id, title=goal[:80])
        db.session.add(session)
        db.session.flush()
        session_id = session.session_id
    else:
        session = ChatSession.query.filter_by(session_id=session_id, user_id=user.user_id).first()
        if session is None:
            session = ChatSession(session_id=session_id, user_id=user.user_id, title=goal[:80])
            db.session.add(session)
            db.session.flush()
            session_id = session.session_id

    referenced_asset_ids = data.get("referenced_asset_ids") or []
    msg = Message(
        session_id=session_id,
        user_id=user.user_id,
        role="user",
        content=goal,
        referenced_asset_ids=__import__("json").dumps(referenced_asset_ids),
    )
    db.session.add(msg)

    run_id = uuid.uuid4().hex
    run = AgentRun(
        run_id=run_id,
        user_id=user.user_id,
        session_id=session_id,
        goal=goal,
        status="queued",
    )
    db.session.add(run)
    db.session.commit()

    plan = plan_goal(goal, user.user_id)
    run.plan_json = __import__("json").dumps(plan)
    db.session.commit()

    stop_run_keepalive(run_id)
    start_run_keepalive(run_id)

    app = current_app._get_current_object()

    def _worker():
        with app.app_context():
            try:
                executor_module.run_workflow(
                    run_id, user.user_id, goal, plan, attached_asset_ids=referenced_asset_ids
                )
            finally:
                stop_run_keepalive(run_id)

    threading.Thread(target=_worker, daemon=True).start()

    return jsonify({"run_id": run_id, "session_id": session_id}), 202


@bp.get("/runs/<run_id>/events")
@auth_required
def run_events(run_id):
    user = _require_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401
    after = request.args.get("after", "-1")
    try:
        after_seq = int(after)
    except (TypeError, ValueError):
        after_seq = -1
    events = get_events(run_id, user.user_id, after_seq=after_seq)
    run = AgentRun.query.filter_by(run_id=run_id, user_id=user.user_id).first()
    status = run.status if run else "unknown"
    return jsonify({"events": events, "status": status})


@bp.post("/ingest")
@auth_required
def ingest():
    user = _require_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401

    if "file" not in request.files:
        return jsonify({"error": "file is required"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"error": "empty file"}), 400

    data = f.read()
    if not data:
        return jsonify({"error": "empty file"}), 400

    try:
        asset = ingest_bytes(
            data,
            filename=f.filename,
            mime_type=f.content_type or "application/octet-stream",
            user_id=user.user_id,
            title=f.filename,
        )
    except Exception as exc:
        return jsonify({"error": f"ingest failed: {exc}"}), 500

    return jsonify(
        {
            "asset_id": asset.id,
            "title": asset.title,
            "content_type": asset.content_type,
            "status": asset.status,
        }
    ), 201


@bp.get("/heartbeat")
@auth_required
def heartbeat():
    return jsonify({"ok": True})


@bp.get("/assets")
@auth_required
def list_assets():
    user = _require_user()
    assets = (
        Asset.query.filter_by(user_id=user.user_id)
        .order_by(Asset.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        [
            {"id": a.id, "title": a.title, "content_type": a.content_type, "status": a.status}
            for a in assets
        ]
    )
