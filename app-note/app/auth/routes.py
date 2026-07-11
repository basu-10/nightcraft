from urllib.parse import urlsplit

from flask import Blueprint, request, jsonify, session, redirect, url_for, render_template, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
import secrets

from ..database import get_connection

auth_bp = Blueprint("auth", __name__)


def _normalize_next_target(raw_target: str | None, fallback: str):
    candidate = (raw_target or fallback or "/").strip()
    parsed = urlsplit(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    return candidate


def _json_or_redirect(is_json: bool, msg: str, code: int, redirect_to: str):
    if is_json:
        return jsonify({"error": msg}), code
    flash(msg, "error")
    return redirect(url_for(redirect_to))


# ── Register ──────────────────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("auth/register.html")

    is_json = request.is_json
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    timezone = (data.get("timezone") or "UTC").strip()

    if not username or not email or not password:
        return _json_or_redirect(is_json, "All fields are required.", 400, "auth.register")
    if len(username) < 3:
        return _json_or_redirect(is_json, "Username must be at least 3 characters.", 400, "auth.register")
    if len(password) < 8:
        return _json_or_redirect(is_json, "Password must be at least 8 characters.", 400, "auth.register")
    if "@" not in email:
        return _json_or_redirect(is_json, "Invalid email address.", 400, "auth.register")

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM users WHERE username=?", (username,)
    ).fetchone()
    if existing:
        conn.close()
        return _json_or_redirect(is_json, "Username already taken.", 409, "auth.register")

    first_user = int(conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]) == 0

    conn.execute(
        "INSERT INTO users (username, email, password, is_admin, timezone) VALUES (?,?,?,?,?)",
        (username, email, generate_password_hash(password), 1 if first_user else 0, timezone),
    )
    conn.commit()
    user = conn.execute("SELECT id, username, timezone FROM users WHERE username=?", (username,)).fetchone()
    conn.close()

    session["user_id"] = user["id"]
    if is_json:
        return jsonify({"id": user["id"], "username": user["username"], "timezone": user["timezone"]}), 201
    return redirect(_normalize_next_target(request.args.get("next"), url_for("main.app_view")))


# ── Login ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("auth/login.html")

    is_json = request.is_json
    data = request.get_json(silent=True) or request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username=?", (username,)
    ).fetchone()
    conn.close()

    if not user or not check_password_hash(user["password"], password):
        return _json_or_redirect(is_json, "Invalid username or password.", 401, "auth.login")

    session["user_id"] = user["id"]
    if is_json:
        return jsonify({"id": user["id"], "username": user["username"], "timezone": user.get("timezone", "UTC")})
    return redirect(_normalize_next_target(request.args.get("next"), url_for("main.app_view")))


# ── Logout ────────────────────────────────────────────────────────────────────

@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


# ── API Token management (for desktop sync) ───────────────────────────────────

@auth_bp.route("/token", methods=["GET"])
def get_token():
    if not g.user_id:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_connection()
    row = conn.execute(
        "SELECT token, label, created_at FROM api_tokens WHERE user_id=?",
        (g.user_id,),
    ).fetchone()
    conn.close()
    return jsonify(dict(row) if row else {"token": None})


@auth_bp.route("/token", methods=["POST"])
def generate_token():
    if not g.user_id:
        return jsonify({"error": "Not authenticated"}), 401
    is_json = request.is_json
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "desktop").strip()

    new_token = secrets.token_urlsafe(32)
    conn = get_connection()
    conn.execute("DELETE FROM api_tokens WHERE user_id=?", (g.user_id,))
    conn.execute(
        "INSERT INTO api_tokens (user_id, token, label) VALUES (?,?,?)",
        (g.user_id, new_token, label),
    )
    conn.commit()
    conn.close()

    if is_json:
        return jsonify({"token": new_token, "label": label}), 201
    flash("New API token generated. Copy it now — it won't be shown again.", "success")
    return redirect(url_for("main.settings_view"))


@auth_bp.route("/token", methods=["DELETE"])
def revoke_token():
    if not g.user_id:
        return jsonify({"error": "Not authenticated"}), 401
    conn = get_connection()
    conn.execute("DELETE FROM api_tokens WHERE user_id=?", (g.user_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@auth_bp.route("/me/timezone", methods=["PUT"])
def update_timezone():
    if not g.user_id:
        return jsonify({"error": "Not authenticated"}), 401
    data = request.get_json(silent=True) or request.form
    tz = (data.get("timezone") or "").strip()
    if not tz:
        return jsonify({"error": "Timezone is required."}), 400
    try:
        from zoneinfo import ZoneInfo
        from datetime import datetime as _dt
        _dt.now(ZoneInfo(tz))
    except Exception:
        return jsonify({"error": "Invalid timezone."}), 400
    from ..database import update_user_timezone
    ok = update_user_timezone(g.user_id, tz)
    if not ok:
        return jsonify({"error": "Failed to update timezone."}), 500
    return jsonify({"timezone": tz})
