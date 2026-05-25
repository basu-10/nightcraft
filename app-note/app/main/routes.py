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
)
from ..sync_logging import get_sync_log_path

main_bp = Blueprint("main", __name__)


def _require_login():
    if not g.user_id:
        return redirect(url_for("auth.login", next=request.full_path if request.query_string else request.path))
    return None


@main_bp.route("/")
def index():
    user = get_user_by_id(g.user_id) if g.user_id else None
    return render_template("landing.html", user=user, is_authenticated=bool(g.user_id))


@main_bp.route("/app")
def app_view():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    user = get_user_by_id(g.user_id)
    return render_template("app.html", user=user)


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
