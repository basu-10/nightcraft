from flask import Blueprint, Response, g, redirect, url_for, render_template, request, flash
from werkzeug.security import generate_password_hash

from ..database import (
    get_user_by_id,
    is_user_admin,
    get_admin_dashboard_stats,
    get_admin_user_overview,
    set_user_admin,
    update_user_password_hash,
    delete_user,
    get_usage_summary,
    get_usage_events,
    get_usage_filter_options,
    get_usage_event,
    delete_usage_event,
    clear_usage_events,
)
from ..sync_logging import get_sync_log_path

main_bp = Blueprint("main", __name__)


def _require_login():
    if not g.user_id:
        return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
    return None


def _guest_user_view():
    return {
        "id": None,
        "username": "Guest",
        "email": "",
        "timezone": "UTC",
    }


@main_bp.route("/")
def index():
    user = get_user_by_id(g.user_id) if g.user_id else None
    return render_template("landing.html", user=user, is_authenticated=bool(g.user_id))


@main_bp.route("/app")
def app_view():
    user = get_user_by_id(g.user_id) if g.user_id else _guest_user_view()
    return render_template("app.html", user=user, is_guest=not bool(g.user_id))


@main_bp.route("/settings")
def settings_view():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    user = get_user_by_id(g.user_id)
    return render_template("settings.html", user=user)


@main_bp.route("/sync-log")
def sync_log_view():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none

    log_path = get_sync_log_path()
    try:
        content = log_path.read_text(encoding="utf-8")
    except OSError:
        content = ""
    return Response(content, mimetype="text/plain; charset=utf-8")


def _require_admin():
    if not g.user_id:
        return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
    if not is_user_admin(g.user_id):
        flash("Admin access required.", "error")
        return redirect(url_for("main.app_view"))
    return None


@main_bp.route("/admin")
def admin_view():
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none
    user = get_user_by_id(g.user_id)
    stats = get_admin_dashboard_stats()
    users = get_admin_user_overview()
    return render_template("admin.html", user=user, stats=stats, users=users)


@main_bp.route("/admin/users/<int:target_user_id>/toggle-admin", methods=["POST"])
def admin_toggle_user_admin(target_user_id):
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    target = get_user_by_id(target_user_id)
    if not target:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_view"))

    make_admin = not bool(target.get("is_admin"))
    if not make_admin:
        stats = get_admin_dashboard_stats()
        if stats["admins"] <= 1:
            flash("Cannot remove admin from the last remaining admin account.", "error")
            return redirect(url_for("main.admin_view"))
        if target_user_id == g.user_id:
            flash("Use a different admin account before removing your own admin role.", "error")
            return redirect(url_for("main.admin_view"))

    if set_user_admin(target_user_id, make_admin):
        flash(
            f"User {target['username']} is now {'an admin' if make_admin else 'a regular user'}.",
            "success",
        )
    else:
        flash("Failed to update admin status.", "error")
    return redirect(url_for("main.admin_view"))


@main_bp.route("/admin/users/<int:target_user_id>/reset-password", methods=["POST"])
def admin_reset_user_password(target_user_id):
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    new_password = (request.form.get("new_password") or "").strip()
    if len(new_password) < 8:
        flash("Password must be at least 8 characters.", "error")
        return redirect(url_for("main.admin_view"))

    updated = update_user_password_hash(target_user_id, generate_password_hash(new_password))
    if updated:
        flash("Password updated.", "success")
    else:
        flash("User not found.", "error")
    return redirect(url_for("main.admin_view"))


@main_bp.route("/admin/users/<int:target_user_id>/delete", methods=["POST"])
def admin_delete_user(target_user_id):
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    if target_user_id == g.user_id:
        flash("You cannot delete your own account from admin panel.", "error")
        return redirect(url_for("main.admin_view"))

    target = get_user_by_id(target_user_id)
    if not target:
        flash("User not found.", "error")
        return redirect(url_for("main.admin_view"))

    if target.get("is_admin"):
        stats = get_admin_dashboard_stats()
        if stats["admins"] <= 1:
            flash("Cannot delete the last admin account.", "error")
            return redirect(url_for("main.admin_view"))

    if delete_user(target_user_id):
        flash(f"Deleted user {target['username']}.", "success")
    else:
        flash("Failed to delete user.", "error")
    return redirect(url_for("main.admin_view"))


# ── Usage analytics (per-app admin dashboard) ──────────────────────────────────

def _parse_usage_filters():
    # Read from request.values so the same helper works for GET (view/export)
    # and POST (clear filtered) without duplicating logic.
    raw_user = request.values.get("user_id", "").strip()
    user_id = int(raw_user) if raw_user.isdigit() else None
    event_type = (request.values.get("event_type") or "").strip() or None
    date_from = (request.values.get("date_from") or "").strip() or None
    date_to = (request.values.get("date_to") or "").strip() or None
    search = (request.values.get("q") or "").strip() or None
    return user_id, event_type, date_from, date_to, search


@main_bp.route("/admin/usage")
def admin_usage_view():
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    user_id, event_type, date_from, date_to, search = _parse_usage_filters()
    try:
        days = max(1, min(int(request.args.get("days", 30)), 365))
    except (TypeError, ValueError):
        days = 30
    try:
        per_page = max(10, min(int(request.args.get("per_page", 50)), 200))
    except (TypeError, ValueError):
        per_page = 50
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    offset = (page - 1) * per_page

    summary = get_usage_summary(days=days)
    result = get_usage_events(
        user_id=user_id,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=per_page,
        offset=offset,
    )
    options = get_usage_filter_options()

    total_pages = max(1, (result["total"] + per_page - 1) // per_page)
    user_map = {int(u["id"]): u["username"] for u in options["users"]}

    return render_template(
        "usage.html",
        user=get_user_by_id(g.user_id),
        summary=summary,
        events=result["events"],
        total_events=result["total"],
        options=options,
        user_map=user_map,
        filters={
            "user_id": user_id or "",
            "event_type": event_type or "",
            "date_from": date_from or "",
            "date_to": date_to or "",
            "q": search or "",
            "days": days,
            "per_page": per_page,
        },
        page=page,
        total_pages=total_pages,
    )


@main_bp.route("/admin/usage/export")
def admin_usage_export():
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    user_id, event_type, date_from, date_to, search = _parse_usage_filters()
    fmt = (request.args.get("format") or "csv").strip().lower()
    result = get_usage_events(
        user_id=user_id,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
        search=search,
        limit=100000,
        offset=0,
    )
    events = result["events"]
    user_map = {
        int(u["id"]): u["username"]
        for u in get_usage_filter_options()["users"]
    }

    if fmt == "json":
        import json as _json
        payload = [
            {
                "id": e["id"],
                "user_id": e["user_id"],
                "username": user_map.get(int(e["user_id"])) if e["user_id"] else None,
                "event_type": e["event_type"],
                "event_detail": e.get("event_detail_parsed") or e.get("event_detail"),
                "ip_address": e.get("ip_address"),
                "user_agent": e.get("user_agent"),
                "status_code": e.get("status_code"),
                "created_at": e.get("created_at"),
            }
            for e in events
        ]
        body = _json.dumps(payload, indent=2, default=str)
        return Response(
            body,
            mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=notestack_usage_events.json"},
        )

    # Default: CSV
    import csv
    import io
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "id", "timestamp", "user_id", "username", "event_type",
        "event_detail", "ip_address", "user_agent", "status_code",
    ])
    for e in events:
        username = user_map.get(int(e["user_id"])) if e["user_id"] else ""
        detail = e.get("event_detail") or ""
        writer.writerow([
            e["id"], e.get("created_at", ""), e["user_id"] or "", username or "",
            e["event_type"], detail, e.get("ip_address") or "",
            e.get("user_agent") or "", e.get("status_code") or "",
        ])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=notestack_usage_events.csv"},
    )


@main_bp.route("/admin/usage/events/<int:event_id>/delete", methods=["POST"])
def admin_usage_delete_event(event_id):
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    event = get_usage_event(event_id)
    if not event:
        flash("Usage event not found.", "error")
        return redirect(url_for("main.admin_usage_view"))

    if delete_usage_event(event_id):
        flash("Usage event deleted.", "success")
    else:
        flash("Failed to delete usage event.", "error")
    return redirect(url_for("main.admin_usage_view", **_parse_usage_filters_as_dict()))


@main_bp.route("/admin/usage/clear", methods=["POST"])
def admin_usage_clear():
    redirect_or_none = _require_admin()
    if redirect_or_none:
        return redirect_or_none

    user_id, event_type, date_from, date_to, search = _parse_usage_filters()
    # Management clear only honours structural filters, never free-text search,
    # so admins explicitly scope what they wipe (user / type / date range).
    deleted = clear_usage_events(
        user_id=user_id,
        event_type=event_type,
        date_from=date_from,
        date_to=date_to,
    )
    flash(f"Cleared {deleted} usage event(s).", "success")
    return redirect(url_for("main.admin_usage_view"))


def _parse_usage_filters_as_dict():
    user_id, event_type, date_from, date_to, search = _parse_usage_filters()
    return {
        "user_id": user_id or "",
        "event_type": event_type or "",
        "date_from": date_from or "",
        "date_to": date_to or "",
        "q": search or "",
    }
