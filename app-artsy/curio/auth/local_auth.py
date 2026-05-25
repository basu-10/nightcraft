from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import LocalCredential

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _forwarded_prefix() -> str:
    raw_prefix = (request.headers.get("X-Forwarded-Prefix") or "").strip()
    if not raw_prefix:
        return ""
    normalized = f"/{raw_prefix.strip('/')}"
    return "" if normalized == "/" else normalized


def _normalize_next_target(raw_target: str | None, fallback: str) -> str:
    candidate = (raw_target or fallback or "/").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        candidate = fallback
        parsed = urlsplit(candidate)

    path = parsed.path or "/"
    prefix = _forwarded_prefix()
    if prefix and path != prefix and not path.startswith(f"{prefix}/"):
        path = f"{prefix}{path}" if path.startswith("/") else f"{prefix}/{path}"

    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = LocalCredential.query.filter_by(username=username).first()
        if user and user.check_password(password):
            user.ensure_profile()
            db.session.commit()
            login_user(user)
            next_url = _normalize_next_target(request.args.get("next"), url_for("main.home"))
            return redirect(next_url)
        flash("Invalid credentials.", "error")

    admin_path = current_app.config.get("ADMIN_APP_PATH", "/admin")
    auth_login_path = current_app.config.get("AUTH_LOGIN_PATH", "/auth/login")
    auth_return_param = current_app.config.get("AUTH_RETURN_PARAM", "next")
    admin_login_url = f"{auth_login_path}?{auth_return_param}={admin_path}"

    return render_template(
        "auth/login.html",
        admin_login_url=admin_login_url,
        has_admin_login=True,
    )


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return render_template("auth/register.html")

        existing = LocalCredential.query.filter_by(username=username).first()
        if existing:
            flash("Username already exists.", "error")
            return render_template("auth/register.html")

        user = LocalCredential(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
        user.ensure_profile()
        db.session.commit()
        login_user(user)
        return redirect(url_for("main.home"))

    return render_template("auth/register.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.home"))
