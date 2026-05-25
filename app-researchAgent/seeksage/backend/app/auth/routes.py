import secrets
import json
from urllib.parse import quote, urlsplit
from urllib import request as urllib_request
from urllib.error import URLError

from flask import Blueprint, current_app, jsonify, request
from flask import redirect, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..models import User

try:
    from authlib.integrations.base_client import OAuthError
except ImportError:
    OAuthError = None


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = None


def init_sso(app):
    global oauth
    if app.config.get("AUTH_MODE", "local") != "sso":
        return

    if oauth is not None:
        return

    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError as exc:
        raise RuntimeError("Authlib is required for AUTH_MODE=sso") from exc

    oauth = OAuth(app)
    oauth.register(
        "auth_service",
        client_id=app.config.get("AUTHLIB_CLIENT_ID", "seeksage-app"),
        client_secret=app.config.get("AUTHLIB_CLIENT_SECRET", "dev-secret"),
        server_metadata_url=(
            f"{app.config.get('AUTH_SERVICE_URL', 'http://127.0.0.1:5100')}"
            "/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email"},
    )


def _safe_next_target(raw_next: str | None) -> str:
    fallback = (current_app.config.get("SSO_DEFAULT_NEXT", "/") or "/").strip()
    target = (raw_next or fallback).strip()

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        target = fallback
        parsed = urlsplit(target)

    path = parsed.path or "/"
    prefix = (request.headers.get("X-Forwarded-Prefix") or "").strip()
    normalized_prefix = f"/{prefix.strip('/')}" if prefix else ""
    if normalized_prefix == "/":
        normalized_prefix = ""

    if normalized_prefix and path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
        path = f"{normalized_prefix}{path}" if path.startswith("/") else f"{normalized_prefix}/{path}"

    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _normalize_roles(raw_roles, derived_is_admin=False):
    if isinstance(raw_roles, str):
        roles = [raw_roles]
    elif isinstance(raw_roles, (list, tuple, set)):
        roles = list(raw_roles)
    else:
        roles = []

    normalized_roles = []
    for role in roles:
        role_value = str(role).strip().lower()
        if role_value and role_value not in normalized_roles:
            normalized_roles.append(role_value)

    if derived_is_admin and "admin" not in normalized_roles:
        normalized_roles.append("admin")

    return normalized_roles


def _auth_logout_url(next_target: str) -> str:
    auth_base = (current_app.config.get("AUTH_SERVICE_URL", "") or "").strip().rstrip("/")
    if not auth_base:
        return next_target
    return f"{auth_base}/logout?next={quote(next_target, safe='')}"


def _session_me_url() -> str:
    configured = (current_app.config.get("AUTH_SESSION_ME_URL", "") or "").strip()
    if configured:
        return configured

    auth_base = (current_app.config.get("AUTH_SERVICE_URL", "") or "").strip().rstrip("/")
    if not auth_base:
        return ""
    return f"{auth_base}/session/me"


def _claims_from_shared_session():
    endpoint = _session_me_url()
    if not endpoint:
        return None

    req = urllib_request.Request(
        endpoint,
        method="GET",
        headers={
            "Accept": "application/json",
            "Cookie": request.headers.get("Cookie", ""),
            "X-Forwarded-Prefix": request.headers.get("X-Forwarded-Prefix", ""),
        },
    )

    try:
        with urllib_request.urlopen(req, timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, ValueError, OSError):
        return None

    if not isinstance(payload, dict) or not payload.get("authenticated"):
        return None

    user_claims = payload.get("user") or {}
    if not isinstance(user_claims, dict):
        return None
    return user_claims


def _upsert_user_from_claims(user_info: dict):
    subject = user_info.get("sub")
    email = (user_info.get("email") or "").strip().lower()
    if not email:
        preferred_username = (user_info.get("preferred_username") or "").strip().lower()
        seed = preferred_username or (str(subject) if subject else "user")
        email = f"{seed}@auth.local"

    roles = _normalize_roles(user_info.get("roles"), derived_is_admin=bool(user_info.get("is_admin", False)))
    is_admin = "admin" in roles

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(email=email, is_admin=is_admin, active=True)
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
    else:
        user.is_admin = is_admin
        user.active = True

    db.session.commit()
    return user


def bridge_shared_auth_session():
    if current_app.config.get("AUTH_MODE", "local") != "sso":
        return
    if current_user.is_authenticated:
        return

    user_info = _claims_from_shared_session()
    if not user_info:
        return

    try:
        user = _upsert_user_from_claims(user_info)
        login_user(user)
    except Exception:
        db.session.rollback()


@auth_bp.get("/sso/login")
def sso_login():
    if oauth is None:
        return jsonify({"error": "SSO is not initialized."}), 503

    session["sso_next"] = _safe_next_target(request.args.get("next"))
    redirect_uri = url_for("auth.sso_callback", _external=True)
    return oauth.auth_service.authorize_redirect(redirect_uri)


@auth_bp.get("/sso/callback")
def sso_callback():
    if oauth is None:
        return jsonify({"error": "SSO is not initialized."}), 503

    try:
        token = oauth.auth_service.authorize_access_token()
    except Exception as exc:
        if OAuthError is not None and isinstance(exc, OAuthError):
            return jsonify({"error": getattr(exc, "description", "Invalid OAuth callback state")}), 400
        raise

    user_info = token.get("userinfo") or {}
    if not user_info:
        try:
            user_info = oauth.auth_service.userinfo(token=token) or {}
        except Exception:
            user_info = {}

    subject = user_info.get("sub") or token.get("sub")
    email = (user_info.get("email") or "").strip().lower()
    if not email:
        preferred_username = (user_info.get("preferred_username") or "").strip().lower()
        seed = preferred_username or (str(subject) if subject else "user")
        email = f"{seed}@auth.local"

    user_info = dict(user_info)
    if subject and not user_info.get("sub"):
        user_info["sub"] = subject
    if email and not user_info.get("email"):
        user_info["email"] = email

    user = _upsert_user_from_claims(user_info)
    login_user(user)

    next_target = _safe_next_target(session.pop("sso_next", None))
    return redirect(next_target)


@auth_bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    existing = User.query.filter_by(email=email).first()
    if existing:
        return jsonify({"error": "Email is already registered."}), 409

    user = User(email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    login_user(user)
    return jsonify({"id": user.id, "email": user.email}), 201


@auth_bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password."}), 401

    login_user(user)
    return jsonify({"id": user.id, "email": user.email}), 200


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    if current_app.config.get("AUTH_MODE", "local") == "sso":
        next_target = _safe_next_target(request.args.get("next") or "/login")
        return jsonify({"ok": True, "logout_url": _auth_logout_url(next_target)}), 200
    return jsonify({"ok": True}), 200


@auth_bp.get("/sso/logout")
def sso_logout():
    logout_user()
    next_target = _safe_next_target(request.args.get("next") or "/login")
    return redirect(_auth_logout_url(next_target))


@auth_bp.post("/change-password")
@login_required
def change_password():
    payload = request.get_json(silent=True) or {}
    current_password = payload.get("current_password") or ""
    new_password = payload.get("new_password") or ""
    if not current_user.check_password(current_password):
        return jsonify({"error": "Current password is incorrect."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "New password must be at least 8 characters."}), 400
    current_user.set_password(new_password)
    db.session.commit()
    return jsonify({"ok": True}), 200


@auth_bp.get("/me")
def me():
    if not current_user.is_authenticated:
        return jsonify({"authenticated": False, "auth_mode": current_app.config.get("AUTH_MODE", "local")}), 200
    return jsonify(
        {
            "authenticated": True,
            "auth_mode": current_app.config.get("AUTH_MODE", "local"),
            "user": {
                "id": current_user.id,
                "email": current_user.email,
                "is_admin": current_user.is_admin,
            },
        }
    ), 200
