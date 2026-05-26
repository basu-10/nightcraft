from urllib.parse import urlsplit

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import current_user, logout_user


main_bp = Blueprint("main", __name__, url_prefix="/ui")


NAV_ITEMS = [
    {"endpoint": "main.dashboard", "label": "Dashboard"},
    {"endpoint": "main.notes", "label": "Notes"},
    {"endpoint": "main.notifications", "label": "Notifications"},
    {"endpoint": "main.settings", "label": "Global Settings"},
    {"endpoint": "main.account", "label": "Account"},
]


def _safe_next_target(raw_next: str | None, fallback_endpoint: str = "main.dashboard") -> str:
    fallback = url_for(fallback_endpoint)
    target = (raw_next or fallback).strip()
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return fallback
    return target


def _require_login():
    if current_user.is_authenticated:
        return None
    return redirect(url_for("main.login", next=request.full_path if request.query_string else request.path))


@main_bp.app_context_processor
def _inject_ui_context():
    return {
        "ui_nav_items": NAV_ITEMS,
    }


@main_bp.get("/")
def ui_root():
    return redirect(url_for("main.dashboard"))


@main_bp.get("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    next_target = _safe_next_target(request.args.get("next"))
    if current_app.config.get("AUTH_MODE", "local") == "sso":
        return redirect(url_for("auth.sso_login", next=next_target))

    return render_template("main/login.html", next_target=next_target)


@main_bp.get("/logout")
def logout():
    logout_user()
    next_target = url_for("main.login")
    if current_app.config.get("AUTH_MODE", "local") == "sso":
        return redirect(url_for("auth.sso_logout", next=next_target))
    return redirect(next_target)


@main_bp.get("/dashboard")
def dashboard():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    return render_template("main/dashboard.html", page_title="Dashboard")


@main_bp.get("/notes")
def notes():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    return render_template("main/notes.html", page_title="Notes")


@main_bp.get("/notifications")
def notifications():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    return render_template("main/coming_soon.html", page_title="Notifications")


@main_bp.get("/global-settings")
def settings():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    return render_template("main/coming_soon.html", page_title="Global Settings")


@main_bp.get("/account")
def account():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    return render_template("main/coming_soon.html", page_title="Account")


@main_bp.get("/admin")
def admin():
    redirect_or_none = _require_login()
    if redirect_or_none:
        return redirect_or_none
    if not current_user.is_admin:
        return redirect(url_for("main.dashboard"))
    return render_template("main/coming_soon.html", page_title="Admin")
