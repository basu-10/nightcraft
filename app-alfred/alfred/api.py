"""API blueprint: run lifecycle, event polling, drag-drop ingest, heartbeat."""

from __future__ import annotations

import os
import threading
import uuid

from flask import Blueprint, current_app, jsonify, request

from .agent.executor import run_workflow
from .agent.events import get_events
from .agent.planner import plan_goal, plan_goal_capability
from .agent import executor as executor_module
from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required, require_owned_asset
from .ingest import ingest_bytes
from .keepalive import start_run_keepalive, stop_run_keepalive
from .models import AgentRun, Asset, AssetRelation, ChatSession, Message
from .settings_keys import (
    resolve_cost_budget_usd,
    resolve_idle_timeout_seconds,
    resolve_max_runtime_seconds,
    resolve_token_budget,
)


def _parse_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _pin_input_hash(asset_ids):
    """Artifact Version Pinning (P2 #14): freeze referenced inputs at run-start.

    Hash over (asset_id, content_hash) pairs so a later edit to a referenced
    asset is detectable and does not alter the executed input.
    """
    if not asset_ids:
        return None
    import hashlib

    parts = []
    for aid in asset_ids:
        asset = Asset.query.get(aid)
        if asset is None:
            continue
        parts.append(f"{asset.id}:{asset.content_hash}")
    if not parts:
        return None
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

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
    # Asset isolation (P2 #5): referenced assets must belong to this user.
    validated_refs = []
    for rid in referenced_asset_ids:
        asset = require_owned_asset(rid, user)
        validated_refs.append(asset.id)

    # Runtime policies (P1 #2 / follow-up F1): the client may override an admin
    # setting for this run, but otherwise the admin-configured global bound is
    # used. Explicit override is validated as non-negative; a negative/None from
    # settings means "unbounded".
    import json as _json

    max_runtime_seconds = _parse_int(data.get("max_runtime_seconds"))
    if max_runtime_seconds is None:
        max_runtime_seconds = resolve_max_runtime_seconds()
    idle_timeout_seconds = _parse_int(data.get("idle_timeout_seconds"))
    if idle_timeout_seconds is None:
        idle_timeout_seconds = resolve_idle_timeout_seconds()
    token_budget = _parse_int(data.get("token_budget"))
    if token_budget is None:
        token_budget = resolve_token_budget()
    cost_budget_usd = _parse_float(data.get("cost_budget_usd"))
    if cost_budget_usd is None:
        cost_budget_usd = resolve_cost_budget_usd()

    # N13: fatal-recovery affordance. When the UI re-runs a failed run with
    # "looser limits", force every bound negative (== unbounded) so a prior
    # policy breach (max runtime / idle / token / cost) does not immediately
    # re-abort the re-run. Explicit per-field overrides above still win.
    relax_bounds = bool(data.get("relax_bounds"))

    run_id = uuid.uuid4().hex

    msg = Message(
        session_id=session_id,
        user_id=user.user_id,
        role="user",
        content=goal,
        referenced_asset_ids=_json.dumps(validated_refs),
    )
    db.session.add(msg)

    # Determinism provenance (P2 #13/#14).
    cap = plan_goal_capability(goal, user.user_id)
    run = AgentRun(
        run_id=run_id,
        user_id=user.user_id,
        session_id=session_id,
        goal=goal,
        status="queued",
        max_runtime_seconds=None if (max_runtime_seconds < 0 or relax_bounds) else max_runtime_seconds,
        idle_timeout_seconds=None if (idle_timeout_seconds < 0 or relax_bounds) else idle_timeout_seconds,
        token_budget=None if (token_budget < 0 or relax_bounds) else token_budget,
        cost_budget_usd=None if (cost_budget_usd < 0 or relax_bounds) else cost_budget_usd,
        capability=cap.get("capability"),
        capability_version=cap.get("capability_version"),
        manifest_hash=cap.get("manifest_hash"),
        run_input_hash=_pin_input_hash(validated_refs),
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
                    run_id, user.user_id, goal, plan, attached_asset_ids=validated_refs
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


@bp.delete("/assets/<int:asset_id>/relations/<int:to_id>")
@auth_required
def delete_asset_relation(asset_id, to_id):
    """N4: remove an AssetRelation (provenance edge).

    Asset isolation (P2 #5): the caller must own BOTH endpoints of the edge, so a
    user cannot orphan provenance that points at another user's data. Returns 204
    on success, 404 if the edge does not exist (or is not owned by this user).
    """
    user = _require_user()
    if user is None:
        return jsonify({"error": "unauthorized"}), 401

    # Ownership of both sides is enforced before any delete (F5/N4 closure).
    require_owned_asset(asset_id, user)
    require_owned_asset(to_id, user)

    relation = AssetRelation.query.filter_by(from_id=asset_id, to_id=to_id).first()
    if relation is None:
        return jsonify({"error": "relation not found"}), 404
    db.session.delete(relation)
    db.session.commit()
    return "", 204
