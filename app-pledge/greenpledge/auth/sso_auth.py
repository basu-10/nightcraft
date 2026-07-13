from urllib.parse import quote, urlsplit

from flask import Blueprint, abort, current_app, redirect, request, session, url_for

from ..extensions import db
from ..models import UserProfile

try:
    from authlib.integrations.base_client import OAuthError
except ImportError:
    OAuthError = None

bp = Blueprint("auth", __name__, url_prefix="/auth")
oauth = None


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


def _build_auth_logout_url(next_target: str) -> str:
    auth_base = (current_app.config.get("AUTH_SERVICE_URL", "") or "").strip().rstrip("/")
    if not auth_base:
        return next_target
    return f"{auth_base}/logout?next={quote(next_target, safe='')}"


def init_sso(app):
    global oauth
    if oauth is not None:
        return

    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError as exc:
        raise RuntimeError("Authlib is required for AUTH_MODE=sso") from exc

    oauth = OAuth(app)
    oauth.register(
        "auth_service",
        client_id=app.config.get("AUTHLIB_CLIENT_ID", "green-pledge-app"),
        client_secret=app.config.get("AUTHLIB_CLIENT_SECRET", "dev-secret"),
        server_metadata_url=(
            f"{app.config.get('AUTH_SERVICE_URL', 'http://localhost/auth')}"
            "/.well-known/openid-configuration"
        ),
        client_kwargs={"scope": "openid profile email"},
    )


@bp.route("/register", methods=["GET"])
def register():
    auth_base = (current_app.config.get("AUTH_SERVICE_URL", "") or "").strip().rstrip("/")
    if not auth_base:
        return redirect(url_for("landing.home"))
    return redirect(f"{auth_base}/register")


@bp.route("/login")
def login():
    if oauth is None:
        abort(500, "SSO is not initialized")
    session["sso_next"] = _normalize_next_target(request.args.get("next"), url_for("landing.home"))
    redirect_uri = url_for("auth.callback", _external=True)
    return oauth.auth_service.authorize_redirect(redirect_uri)


@bp.route("/callback")
def callback():
    if oauth is None:
        abort(500, "SSO is not initialized")

    try:
        token = oauth.auth_service.authorize_access_token()
    except Exception as exc:
        if OAuthError is not None and isinstance(exc, OAuthError):
            abort(400, getattr(exc, "description", "Invalid OAuth callback state"))
        raise

    user_info = token.get("userinfo") or {}
    if not user_info:
        try:
            user_info = oauth.auth_service.userinfo(token=token) or {}
        except Exception:
            user_info = {}
    subject = user_info.get("sub") or token.get("sub")
    if not subject:
        abort(400, "Missing user subject in token")

    username = user_info.get("preferred_username") or user_info.get("name") or ""
    roles = _normalize_roles(user_info.get("roles"), derived_is_admin=bool(user_info.get("is_admin", False)))
    is_admin = "admin" in roles
    timezone_name = user_info.get("timezone_name", "Asia/Kolkata")

    profile = UserProfile.query.filter_by(user_id=str(subject)).first()
    if not profile:
        profile = UserProfile(
            user_id=str(subject),
            username=username,
            is_admin=is_admin,
            timezone_name=timezone_name,
        )
        db.session.add(profile)
    else:
        profile.username = username
        profile.is_admin = is_admin
        profile.timezone_name = timezone_name
    db.session.commit()

    session["user_id"] = subject
    session["username"] = profile.username
    session["is_admin"] = bool(profile.is_admin)
    session["timezone_name"] = profile.timezone_name

    next_target = _normalize_next_target(session.pop("sso_next", None), url_for("landing.home"))
    return redirect(next_target)


@bp.route("/logout", methods=["POST"])
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    session.pop("is_admin", None)
    session.pop("timezone_name", None)
    next_target = _normalize_next_target(request.args.get("next"), url_for("landing.home"))
    return redirect(_build_auth_logout_url(next_target))
