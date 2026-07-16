"""Library mode: upload, import-by-URL, list, relations."""

from __future__ import annotations

import json

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required
from .ingest import ingest_bytes
from .models import Asset
from .providers import web_search as web_provider
from .rag import get_relation_graph

bp = Blueprint("library", __name__, url_prefix="/alfred/library")


@bp.route("")
@auth_required
def index():
    user = get_current_user()
    assets = (
        Asset.query.filter_by(user_id=user.user_id)
        .order_by(Asset.created_at.desc())
        .all()
    )
    return render_template("alfred/library.html", assets=assets)


@bp.route("/upload", methods=["POST"])
@auth_required
def upload():
    user = get_current_user()
    if "file" not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("library.index"))
    f = request.files["file"]
    if not f or not f.filename:
        flash("Empty file.", "error")
        return redirect(url_for("library.index"))
    data = f.read()
    if not data:
        flash("Empty file.", "error")
        return redirect(url_for("library.index"))
    try:
        asset = ingest_bytes(
            data,
            filename=f.filename,
            mime_type=f.content_type or "application/octet-stream",
            user_id=user.user_id,
            title=f.filename,
        )
    except Exception as exc:
        flash(f"Ingest failed: {exc}", "error")
        return redirect(url_for("library.index"))
    flash(f"Ingested '{asset.title}'.", "success")
    return redirect(url_for("library.index"))


@bp.route("/import-url", methods=["POST"])
@auth_required
def import_url():
    user = get_current_user()
    url = (request.form.get("url") or "").strip()
    if not url:
        flash("URL is required.", "error")
        return redirect(url_for("library.index"))
    text = web_provider.visit_url(url, max_chars=20000)
    if not text:
        flash("Could not fetch the URL.", "error")
        return redirect(url_for("library.index"))
    try:
        asset = ingest_bytes(
            text.encode("utf-8"),
            filename=url.split("/")[-1] or "web_import",
            mime_type="text/plain",
            user_id=user.user_id,
            title=url,
            source_url=url,
        )
    except Exception as exc:
        flash(f"Import failed: {exc}", "error")
        return redirect(url_for("library.index"))
    flash(f"Imported '{asset.title}'.", "success")
    return redirect(url_for("library.index"))


@bp.route("/asset/<int:asset_id>")
@auth_required
def asset_detail(asset_id):
    user = get_current_user()
    asset = Asset.query.filter_by(id=asset_id, user_id=user.user_id).first_or_404()
    graph = get_relation_graph(asset.id)
    return render_template("alfred/asset.html", asset=asset, graph=graph)


@bp.route("/asset/<int:asset_id>/delete", methods=["POST"])
@auth_required
def delete_asset(asset_id):
    user = get_current_user()
    asset = Asset.query.filter_by(id=asset_id, user_id=user.user_id).first_or_404()
    # Hard delete: remove backing file + cascade chunks/embeddings/relations.
    import os

    try:
        if os.path.exists(asset.storage_ref):
            os.remove(asset.storage_ref)
    except OSError:
        pass
    db.session.delete(asset)
    db.session.commit()
    flash("Asset deleted.", "success")
    return redirect(url_for("library.index"))
