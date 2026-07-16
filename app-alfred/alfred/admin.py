"""Admin blueprint: per-app Alfred settings (admin-only)."""

from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .auth.current_user import get_current_user
from .extensions import db
from .guards import admin_required, auth_required
from .ingest import reindex_library
from .models import Asset
from .services.settings import get_setting, get_setting_int, upsert_setting
from .settings_keys import (
    DEFAULT_AGENT_MODEL,
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_REACT_MAX_STEPS,
    DEFAULT_TOP_K,
    SETTING_AGENT_MODEL,
    SETTING_CHUNK_OVERLAP,
    SETTING_CHUNK_SIZE,
    SETTING_EMBEDDING_MODEL,
    SETTING_OPENROUTER_API_KEY,
    SETTING_REACT_MAX_STEPS,
    SETTING_TOP_K,
)

bp = Blueprint("admin", __name__, url_prefix="/alfred/admin")


@bp.route("")
@auth_required
@admin_required
def dashboard():
    return redirect(url_for("admin.settings"))


@bp.route("/settings", methods=["GET", "POST"])
@auth_required
@admin_required
def settings():
    user = get_current_user()
    if request.method == "POST":
        api_key = request.form.get("alfred_openrouter_api_key", "").strip()
        embedding_model = request.form.get("alfred_embedding_model", "").strip()
        agent_model = request.form.get("alfred_agent_model", "").strip()
        max_steps = request.form.get("alfred_react_max_steps", "").strip()
        chunk_size = request.form.get("alfred_chunk_size", "").strip()
        chunk_overlap = request.form.get("alfred_chunk_overlap", "").strip()
        top_k = request.form.get("alfred_top_k", "").strip()

        if api_key:
            db.session.add(upsert_setting(SETTING_OPENROUTER_API_KEY, api_key, encrypted=True))
        if embedding_model:
            db.session.add(upsert_setting(SETTING_EMBEDDING_MODEL, embedding_model, encrypted=False))
        if agent_model:
            db.session.add(upsert_setting(SETTING_AGENT_MODEL, agent_model, encrypted=False))
        if max_steps:
            db.session.add(upsert_setting(SETTING_REACT_MAX_STEPS, max_steps, encrypted=False))
        if chunk_size:
            db.session.add(upsert_setting(SETTING_CHUNK_SIZE, chunk_size, encrypted=False))
        if chunk_overlap:
            db.session.add(upsert_setting(SETTING_CHUNK_OVERLAP, chunk_overlap, encrypted=False))
        if top_k:
            db.session.add(upsert_setting(SETTING_TOP_K, top_k, encrypted=False))

        db.session.commit()
        flash("Alfred settings updated.", "success")
        return redirect(url_for("admin.settings"))

    masked_key = "********" if get_setting(SETTING_OPENROUTER_API_KEY, "") else ""
    ctx = {
        "masked_key": masked_key,
        "embedding_model": get_setting(SETTING_EMBEDDING_MODEL, DEFAULT_EMBEDDING_MODEL),
        "agent_model": get_setting(SETTING_AGENT_MODEL, DEFAULT_AGENT_MODEL),
        "react_max_steps": get_setting_int(SETTING_REACT_MAX_STEPS, DEFAULT_REACT_MAX_STEPS),
        "chunk_size": get_setting_int(SETTING_CHUNK_SIZE, DEFAULT_CHUNK_SIZE),
        "chunk_overlap": get_setting_int(SETTING_CHUNK_OVERLAP, DEFAULT_CHUNK_OVERLAP),
        "top_k": get_setting_int(SETTING_TOP_K, DEFAULT_TOP_K),
    }
    return render_template("alfred/admin/settings.html", **ctx)


@bp.route("/settings/reindex", methods=["POST"])
@auth_required
@admin_required
def reindex():
    user = get_current_user()
    try:
        count = reindex_library(user.user_id)
        flash(f"Re-indexed {count} chunk(s) under the active embedding model.", "success")
    except Exception as exc:
        flash(f"Re-index failed: {exc}", "error")
    return redirect(url_for("admin.settings"))
