"""Main web routes: home + Ask Alfred conversation view."""

from __future__ import annotations

from flask import Blueprint, render_template, request, url_for

from .auth.current_user import get_current_user
from .guards import auth_required
from .models import Asset, ChatSession

bp = Blueprint("main", __name__, url_prefix="/alfred")


@bp.route("/")
@auth_required
def home():
    user = get_current_user()
    sessions = (
        ChatSession.query.filter_by(user_id=user.user_id)
        .order_by(ChatSession.updated_at.desc())
        .limit(20)
        .all()
    )
    return render_template("alfred/home.html", sessions=sessions)


@bp.route("/ask")
@auth_required
def ask():
    user = get_current_user()
    session_id = request.args.get("session", "").strip()
    session = None
    messages = []
    if session_id:
        session = ChatSession.query.filter_by(session_id=session_id, user_id=user.user_id).first()
        if session:
            from .models import Message

            messages = Message.query.filter_by(session_id=session_id, user_id=user.user_id).order_by(Message.created_at.asc()).all()

    # Assets available to attach (drag-drop or click-to-attach).
    assets = (
        Asset.query.filter_by(user_id=user.user_id, status="ready")
        .order_by(Asset.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template(
        "alfred/ask.html",
        session=session,
        messages=messages,
        assets=assets,
    )


@bp.route("/asset/<int:asset_id>")
@auth_required
def asset_view(asset_id):
    user = get_current_user()
    asset = Asset.query.filter_by(id=asset_id, user_id=user.user_id).first_or_404()
    from .rag import get_relation_graph

    graph = get_relation_graph(asset.id)
    return render_template("alfred/asset.html", asset=asset, graph=graph)
