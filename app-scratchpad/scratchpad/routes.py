"""ScratchPad web + content API routes."""
from __future__ import annotations

import json

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask.views import MethodView

from .auth.current_user import get_current_user
from .extensions import db
from .guards import auth_required
from .models import Pad

bp = Blueprint("app", __name__, url_prefix="/scratchpad")

# Root route (no prefix). The on-demand runtime manager probes `GET /` to
# decide when the service is ready; without this the probe gets a 404 and the
# branded loader page polls forever. It also hands off to the /scratchpad landing.
_root_bp = Blueprint("app_root", __name__)


@_root_bp.route("/")
def root():
    return redirect(url_for("app.landing"))


@bp.route("/")
def landing():
    user = get_current_user()
    if user.is_authenticated:
        return redirect(url_for("app.editor"))
    return render_template("scratchpad/landing.html", app_user=user)


@bp.route("/app")
@auth_required
def editor():
    user = get_current_user()
    return render_template("scratchpad/app.html", app_user=user)


@bp.route("/healthz")
def healthz():
    return {"status": "ok", "service": "scratchpad"}, 200


def _require_user_id():
    user = get_current_user()
    if not user.is_authenticated:
        abort(401)
    return user.user_id


class PadAPI(MethodView):
    def get(self, item_id=None):
        user_id = _require_user_id()
        if item_id is None:
            items = (
                Pad.query.filter_by(user_id=user_id)
                .order_by(Pad.updated_at.desc())
                .all()
            )
            return {
                "items": [
                    {
                        "id": i.id,
                        "title": i.title,
                        "content_json": i.content_json,
                        "updated_at": i.updated_at.isoformat(),
                    }
                    for i in items
                ]
            }
        item = Pad.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        return {
            "id": item.id,
            "title": item.title,
            "content_json": item.content_json,
            "updated_at": item.updated_at.isoformat(),
        }

    def post(self):
        user_id = _require_user_id()
        payload = request.get_json(silent=True) or {}
        try:
            content = payload.get("content_json", "{}")
            if not isinstance(content, str):
                content = json.dumps(content)
        except (TypeError, ValueError):
            content = "{}"
        item = Pad(
            user_id=user_id,
            title=(payload.get("title") or "Untitled"),
            content_json=content,
        )
        db.session.add(item)
        db.session.commit()
        return {
            "id": item.id,
            "title": item.title,
            "content_json": item.content_json,
            "updated_at": item.updated_at.isoformat(),
        }, 201

    def put(self, item_id):
        user_id = _require_user_id()
        item = Pad.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        payload = request.get_json(silent=True) or {}
        if "title" in payload:
            item.title = payload["title"]
        if "content_json" in payload:
            content = payload["content_json"]
            if not isinstance(content, str):
                try:
                    content = json.dumps(content)
                except (TypeError, ValueError):
                    content = "{}"
            item.content_json = content
        db.session.commit()
        return {
            "id": item.id,
            "title": item.title,
            "content_json": item.content_json,
            "updated_at": item.updated_at.isoformat(),
        }

    def delete(self, item_id):
        user_id = _require_user_id()
        item = Pad.query.filter_by(id=item_id, user_id=user_id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        return {"status": "deleted", "id": item.id}, 200


bp.add_url_rule("/api/pad", view_func=PadAPI.as_view("pad_list"))
bp.add_url_rule("/api/pad/<int:item_id>", view_func=PadAPI.as_view("pad_item"))
