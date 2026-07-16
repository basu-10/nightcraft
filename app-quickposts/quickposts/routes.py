"""QuickPosts web + content API routes."""
from __future__ import annotations

import json

from flask import Blueprint, abort, get_flashed_messages, redirect, render_template, request, url_for
from flask.views import MethodView

from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required
from .models import QuickPost

bp = Blueprint("app", __name__, url_prefix="/quickposts")


@bp.route("/")
def landing():
    user = get_current_user()
    if user.is_authenticated:
        return redirect(url_for("app.editor"))
    return render_template("quickposts/landing.html", app_user=user)


@bp.route("/app")
@auth_required
def editor():
    user = get_current_user()
    return render_template("quickposts/app.html", app_user=user)


@bp.route("/healthz")
def healthz():
    return {"status": "ok", "service": "quickposts"}, 200


def _require_user_id():
    user = get_current_user()
    if not user.is_authenticated:
        abort(401)
    return user.user_id


class QuickPostAPI(MethodView):
    def get(self, item_id=None):
        user_id = _require_user_id()
        if item_id is None:
            items = (
                QuickPost.query.filter_by(user_id=user_id)
                .order_by(QuickPost.updated_at.desc())
                .all()
            )
            return {
                "items": [
                    {
                        "id": i.id,
                        "title": i.title,
                        "body": i.body,
                        "layout": i.layout,
                        "updated_at": i.updated_at.isoformat(),
                    }
                    for i in items
                ]
            }
        item = QuickPost.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        return {
            "id": item.id,
            "title": item.title,
            "body": item.body,
            "layout": item.layout,
            "updated_at": item.updated_at.isoformat(),
        }

    def post(self):
        user_id = _require_user_id()
        payload = request.get_json(silent=True) or {}
        item = QuickPost(
            user_id=user_id,
            title=(payload.get("title") or "Untitled"),
            body=payload.get("body", ""),
            layout=payload.get("layout", "post"),
        )
        db.session.add(item)
        db.session.commit()
        return {
            "id": item.id,
            "title": item.title,
            "body": item.body,
            "layout": item.layout,
            "updated_at": item.updated_at.isoformat(),
        }, 201

    def put(self, item_id):
        user_id = _require_user_id()
        item = QuickPost.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        payload = request.get_json(silent=True) or {}
        if "title" in payload:
            item.title = payload["title"]
        if "body" in payload:
            item.body = payload["body"]
        if "layout" in payload:
            item.layout = payload["layout"]
        db.session.commit()
        return {
            "id": item.id,
            "title": item.title,
            "body": item.body,
            "layout": item.layout,
            "updated_at": item.updated_at.isoformat(),
        }

    def delete(self, item_id):
        user_id = _require_user_id()
        item = QuickPost.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return {"status": "deleted", "id": item.id}, 200


bp.add_url_rule("/api/quickpost", view_func=QuickPostAPI.as_view("quickpost_list"))
bp.add_url_rule("/api/quickpost/<int:item_id>", view_func=QuickPostAPI.as_view("quickpost_item"))
