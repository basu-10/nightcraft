from datetime import datetime, timedelta, timezone
import base64
import secrets
from urllib.parse import urlencode, urlparse

import jwt
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from .extensions import db
from .models import AuthorizationCode, OauthClient, RefreshToken, Session, User
from .telemetry import emit_login, emit_logout, emit_oauth_login, emit_oauth_register, emit_register, emit_token_issued

try:
    from authlib.integrations.base_client import OAuthError
except ImportError:
    OAuthError = None


bp = Blueprint("core", __name__)
GOOGLE_OAUTH_EXTENSION_KEY = "google_oauth"


def _base_url():
    explicit = current_app.config.get("PUBLIC_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return request.url_root.rstrip("/")


def _utcnow():
    return datetime.now(timezone.utc)


def _session_user_id():
    value = session.get("user_id")
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _current_user():
    user_id = _session_user_id()
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _parse_redirect_uris(client):
    if not client.redirect_uris:
        return set()
    cleaned = []
    for raw in client.redirect_uris.replace("\n", ",").split(","):
        candidate = raw.strip()
        if candidate:
            cleaned.append(candidate)
    return set(cleaned)


def _authorize_error(status_code, error, description):
    return jsonify({"error": error, "error_description": description}), status_code


def _token_error(status_code, error, description):
    return jsonify({"error": error, "error_description": description}), status_code


def _build_authorize_redirect_target(redirect_uri, code, state):
    params = {"code": code}
    if state:
        params["state"] = state
    separator = "&" if "?" in redirect_uri else "?"
    return f"{redirect_uri}{separator}{urlencode(params)}"


def _is_expired(value):
    if value is None:
        return True
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value <= _utcnow()


def _parse_client_credentials():
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Basic "):
        encoded = auth_header.split(" ", 1)[1].strip()
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            client_id, client_secret = decoded.split(":", 1)
            return client_id.strip(), client_secret
        except Exception:
            return None, None

    client_id = request.form.get("client_id", "").strip()
    client_secret = request.form.get("client_secret", "")
    return client_id, client_secret


def _claims_for_user(user):
    roles = ["admin"] if user.is_admin else ["listener"]
    return {
        "sub": str(user.id),
        "preferred_username": user.username,
        "email": user.email,
        "roles": roles,
        "is_admin": bool(user.is_admin),
        "timezone_name": user.timezone_name or "Asia/Kolkata",
    }


def _signing_keys():
    return current_app.extensions["signing_keys"]


def _build_id_token(*, user, client_id, nonce, now, exp):
    issuer = current_app.config.get("OIDC_ISSUER", "").rstrip("/") or _base_url()
    payload = {
        "iss": issuer,
        "aud": client_id,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "auth_time": int(now.timestamp()),
        **_claims_for_user(user),
    }
    if nonce:
        payload["nonce"] = nonce
    keys = _signing_keys()
    return jwt.encode(payload, keys["private_key"], algorithm="RS256", headers={"kid": keys["kid"]})


def _default_timezone():
    return current_app.config.get("DEFAULT_TIMEZONE", "Asia/Kolkata")


def _clean_value(value):
    return str(value or "").strip()


def _normalize_username(username, email=""):
    candidate = _clean_value(username)
    if candidate:
        return candidate

    email_candidate = _clean_value(email)
    if email_candidate and "@" in email_candidate:
        local_part = email_candidate.split("@", 1)[0].strip()
        if local_part:
            return local_part

    return f"user-{secrets.token_hex(3)}"


def _unique_username(base_username, ignore_user_id=None):
    base_candidate = _normalize_username(base_username)
    candidate = base_candidate
    suffix = 2

    while True:
        query = User.query.filter_by(username=candidate)
        if ignore_user_id is not None:
            query = query.filter(User.id != ignore_user_id)
        if query.first() is None:
            return candidate
        candidate = f"{base_candidate}-{suffix}"
        suffix += 1


def _normalize_email(email, username=""):
    candidate = _clean_value(email).lower()
    if candidate:
        return candidate

    username_candidate = _normalize_username(username)
    return f"{username_candidate}@local.invalid"


def _unique_email(base_email, username="", ignore_user_id=None):
    candidate = _normalize_email(base_email, username)
    if "@" not in candidate:
        candidate = f"{_normalize_username(username)}@local.invalid"

    local_part, domain = candidate.split("@", 1)
    suffix = 2

    while True:
        query = User.query.filter_by(email=candidate)
        if ignore_user_id is not None:
            query = query.filter(User.id != ignore_user_id)
        if query.first() is None:
            return candidate
        candidate = f"{local_part}-{suffix}@{domain}"
        suffix += 1


def _normalize_timezone(timezone_name):
    candidate = _clean_value(timezone_name)
    return candidate or _default_timezone()


def _create_session_for_user(user):
    session_token = secrets.token_urlsafe(32)
    expiry = _utcnow() + timedelta(hours=8)

    db.session.add(
        Session(
            user_id=user.id,
            session_token=session_token,
            expires_at=expiry,
        )
    )
    db.session.commit()

    session["user_id"] = str(user.id)
    session["session_token"] = session_token
    return session_token


def _store_post_login_redirect(next_url):
    if next_url:
        session["post_login_redirect"] = next_url


def _consume_post_login_redirect(default=""):
    return session.pop("post_login_redirect", default)


def _normalize_post_login_redirect(next_url, default_target):
    candidate = _clean_value(next_url)
    if not candidate:
        return default_target

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/"):
        return default_target

    prefix = (request.headers.get("X-Forwarded-Prefix") or "").strip()
    normalized_prefix = f"/{prefix.strip('/')}" if prefix else ""
    if normalized_prefix == "/":
        normalized_prefix = ""

    path = parsed.path or "/"

    _auth_internal_prefixes = ("/oauth/", "/login", "/register", "/logout", "/session/", "/healthz")
    if normalized_prefix and any(path.startswith(p) for p in _auth_internal_prefixes):
        if path != normalized_prefix and not path.startswith(f"{normalized_prefix}/"):
            path = f"{normalized_prefix}{path}" if path.startswith("/") else f"{normalized_prefix}/{path}"

    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    return f"{path}{query}{fragment}"


def _normalize_safe_redirect(next_url, default_target):
    candidate = _clean_value(next_url)
    if not candidate:
        return default_target

    parsed = urlparse(candidate)
    if parsed.scheme or parsed.netloc or not candidate.startswith("/"):
        return default_target

    return candidate


def _google_oauth_client():
    oauth = current_app.extensions.get(GOOGLE_OAUTH_EXTENSION_KEY)
    if oauth is None:
        return None

    return getattr(oauth, "google", None)


def init_google_oauth(app):
    google_client_id = app.config.get("GOOGLE_CLIENT_ID", "").strip()
    google_client_secret = app.config.get("GOOGLE_CLIENT_SECRET", "").strip()

    if not google_client_id or not google_client_secret:
        app.extensions[GOOGLE_OAUTH_EXTENSION_KEY] = None
        return

    try:
        from authlib.integrations.flask_client import OAuth
    except ImportError as exc:
        raise RuntimeError("Authlib is required for Google sign-in") from exc

    oauth = OAuth(app)
    oauth.register(
        "google",
        client_id=google_client_id,
        client_secret=google_client_secret,
        server_metadata_url=app.config.get(
            "GOOGLE_DISCOVERY_URL",
            "https://accounts.google.com/.well-known/openid-configuration",
        ),
        client_kwargs={"scope": "openid email profile"},
    )
    app.extensions[GOOGLE_OAUTH_EXTENSION_KEY] = oauth


def _render_login_page(*, next_url="", username_value=""):
    return render_template(
        "auth/login.html",
        next_url=next_url,
        form_values={"username": username_value},
        google_login_url=url_for("core.google_login", next=next_url),
    )


def _render_register_page(*, next_url="", form_values=None):
    return render_template(
        "auth/register.html",
        next_url=next_url,
        default_timezone=_default_timezone(),
        form_values=form_values or {},
    )


@bp.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "service": "service-auth"})


@bp.get("/.well-known/openid-configuration")
def openid_configuration():
    issuer = current_app.config.get("OIDC_ISSUER", "").rstrip("/") or _base_url()

    return jsonify(
        {
            "issuer": issuer,
            "authorization_endpoint": f"{issuer}/oauth/authorize",
            "token_endpoint": f"{issuer}/oauth/token",
            "jwks_uri": f"{issuer}/oauth/jwks",
            "userinfo_endpoint": f"{issuer}/userinfo",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": ["openid", "profile", "email"],
            "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
            "claims_supported": ["sub", "preferred_username", "email", "roles", "is_admin", "timezone_name"],
        }
    )


@bp.get("/oauth/jwks")
def jwks():
    return jsonify({"keys": [_signing_keys()["jwk"]]})


@bp.route("/register", methods=["GET", "POST"])
def register():
    next_url = _clean_value(request.args.get("next", ""))

    if request.method == "GET":
        return _render_register_page(next_url=next_url)

    next_url = _clean_value(request.form.get("next", "") or next_url)
    raw_username = request.form.get("username", "")
    raw_email = request.form.get("email", "")
    password = _clean_value(request.form.get("password", ""))
    timezone_name = _normalize_timezone(request.form.get("timezone_name", ""))

    if not password:
        flash("Password is required.", "error")
        return _render_register_page(
            next_url=next_url,
            form_values={"username": raw_username, "email": raw_email, "timezone_name": request.form.get("timezone_name", "")},
        ), 400

    username = _unique_username(raw_username or raw_email)
    email = _unique_email(raw_email, username)

    if User.query.filter((User.username == username) | (User.email == email)).first():
        flash("Username or email already exists.", "error")
        return _render_register_page(
            next_url=next_url,
            form_values={"username": raw_username, "email": raw_email, "timezone_name": request.form.get("timezone_name", "")},
        ), 409

    user = User(username=username, email=email, timezone_name=timezone_name, is_admin=False)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    _create_session_for_user(user)
    emit_register(user.id, session.get("session_token", ""))

    return redirect(_normalize_post_login_redirect(next_url, url_for("core.login")))


@bp.route("/login", methods=["GET", "POST"])
def login():
    next_url = _clean_value(request.args.get("next", ""))
    if request.method == "GET":
        return _render_login_page(next_url=next_url)

    next_url = _clean_value(request.form.get("next", "") or next_url)
    username = _clean_value(request.form.get("username", ""))
    password = request.form.get("password", "")
    user = User.query.filter((User.username == username) | (User.email == username.lower())).first()

    if not user or not user.check_password(password):
        flash("Invalid credentials.", "error")
        return _render_login_page(next_url=next_url, username_value=username), 401

    _create_session_for_user(user)
    emit_login(user.id, session.get("session_token", ""))
    return redirect(_normalize_post_login_redirect(next_url, url_for("core.healthz")))


@bp.get("/session/me")
def session_me():
    """Return lightweight user claims for callers that share this browser session."""
    user = _current_user()
    if user is None:
        return jsonify({"authenticated": False}), 200

    claims = _claims_for_user(user)
    return jsonify(
        {
            "authenticated": True,
            "user": claims,
        }
    ), 200


@bp.get("/login/google")
def google_login():
    next_url = _clean_value(request.args.get("next", ""))
    google_client = _google_oauth_client()
    if google_client is None:
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("core.login", next=next_url))

    _store_post_login_redirect(next_url)
    return google_client.authorize_redirect(url_for("core.google_callback", _external=True))


@bp.get("/login/google/callback")
def google_callback():
    google_client = _google_oauth_client()
    if google_client is None:
        flash("Google sign-in is not configured yet.", "error")
        return redirect(url_for("core.login"))

    try:
        token = google_client.authorize_access_token()
    except Exception as exc:
        if OAuthError is not None and isinstance(exc, OAuthError):
            flash(getattr(exc, "description", "Invalid Google callback state"), "error")
            return redirect(url_for("core.login"))
        raise

    user_info = token.get("userinfo") or {}
    if not user_info:
        try:
            user_info = google_client.userinfo(token=token) or {}
        except Exception:
            user_info = {}

    email = _clean_value(user_info.get("email", "")).lower()
    if not email:
        abort(400, "Missing Google account email")

    username = _normalize_username(user_info.get("preferred_username") or user_info.get("name", ""), email)
    timezone_name = _normalize_timezone(user_info.get("timezone_name", ""))

    user = User.query.filter_by(email=email).first()
    is_new_user = False
    if user is None:
        if User.query.filter_by(username=username).first():
            username = _unique_username(username)
        user = User(username=username, email=email, timezone_name=timezone_name, is_admin=False)
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        is_new_user = True
    else:
        user.username = _unique_username(username, ignore_user_id=user.id)
        user.timezone_name = timezone_name or user.timezone_name

    db.session.commit()
    _create_session_for_user(user)
    if is_new_user:
        emit_oauth_register(user.id, session.get("session_token", ""))
    else:
        emit_oauth_login(user.id, session.get("session_token", ""))
    return redirect(_normalize_post_login_redirect(_consume_post_login_redirect(""), url_for("core.healthz")))


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    next_url = _normalize_safe_redirect(_clean_value(request.values.get("next", "")), url_for("core.login"))
    session_token = session.get("session_token")
    if session_token:
        Session.query.filter_by(session_token=session_token).delete()
        db.session.commit()

    user_id = session.pop("user_id", None)
    session.pop("session_token", None)
    session.pop("post_login_redirect", None)
    emit_logout(int(user_id) if user_id else None, session_token or "")
    return redirect(next_url)


@bp.get("/oauth/authorize")
def authorize():
    client_id = request.args.get("client_id", "").strip()
    redirect_uri = request.args.get("redirect_uri", "").strip()
    response_type = request.args.get("response_type", "").strip()
    scope = request.args.get("scope", "openid profile email").strip() or "openid profile email"
    state = request.args.get("state", "")
    nonce = request.args.get("nonce", "").strip()

    if not client_id or not redirect_uri or not response_type:
        return _authorize_error(400, "invalid_request", "client_id, redirect_uri and response_type are required")

    if response_type != "code":
        return _authorize_error(400, "unsupported_response_type", "response_type must be code")

    client = OauthClient.query.filter_by(client_id=client_id).first()
    if not client:
        return _authorize_error(400, "invalid_client", "unknown client_id")

    if redirect_uri not in _parse_redirect_uris(client):
        return _authorize_error(400, "invalid_request", "redirect_uri mismatch")

    user = _current_user()
    if not user:
        return redirect(url_for("core.login", next=request.full_path if request.query_string else request.path))

    if "openid" not in scope.split():
        return _authorize_error(400, "invalid_scope", "openid scope is required")

    code_value = secrets.token_urlsafe(32)
    db.session.add(
        AuthorizationCode(
            code=code_value,
            user_id=user.id,
            client_id=client.client_id,
            redirect_uri=redirect_uri,
            scope=scope,
            nonce=nonce or None,
            expires_at=_utcnow() + timedelta(minutes=5),
        )
    )
    db.session.commit()
    return redirect(_build_authorize_redirect_target(redirect_uri, code_value, state))


@bp.post("/oauth/token")
def token():
    grant_type = request.form.get("grant_type", "").strip()
    if grant_type != "authorization_code":
        return _token_error(400, "unsupported_grant_type", "grant_type must be authorization_code")

    client_id, client_secret = _parse_client_credentials()
    if not client_id or not client_secret:
        return _token_error(401, "invalid_client", "client authentication required")

    client = OauthClient.query.filter_by(client_id=client_id).first()
    if not client or client.client_secret != client_secret:
        return _token_error(401, "invalid_client", "invalid client credentials")

    code_value = request.form.get("code", "").strip()
    redirect_uri = request.form.get("redirect_uri", "").strip()
    if not code_value or not redirect_uri:
        return _token_error(400, "invalid_request", "code and redirect_uri are required")

    auth_code = AuthorizationCode.query.filter_by(code=code_value, client_id=client.client_id).first()
    if not auth_code:
        return _token_error(400, "invalid_grant", "invalid authorization code")

    if auth_code.redirect_uri != redirect_uri:
        return _token_error(400, "invalid_grant", "redirect_uri mismatch")

    if auth_code.consumed_at is not None:
        return _token_error(400, "invalid_grant", "authorization code already used")

    if _is_expired(auth_code.expires_at):
        return _token_error(400, "invalid_grant", "authorization code expired")

    user = db.session.get(User, auth_code.user_id)
    if not user:
        return _token_error(400, "invalid_grant", "user no longer exists")

    now = _utcnow()
    access_exp = now + timedelta(minutes=int(current_app.config.get("ACCESS_TOKEN_TTL_MINUTES", 30)))
    refresh_exp = now + timedelta(days=int(current_app.config.get("REFRESH_TOKEN_TTL_DAYS", 14)))
    id_exp = now + timedelta(minutes=int(current_app.config.get("ID_TOKEN_TTL_MINUTES", 30)))
    claims = _claims_for_user(user)

    access_payload = {
        "iss": current_app.config.get("OIDC_ISSUER", "").rstrip("/") or _base_url(),
        "aud": client.client_id,
        "client_id": client.client_id,
        "scope": auth_code.scope,
        "iat": int(now.timestamp()),
        "exp": int(access_exp.timestamp()),
        "jti": secrets.token_urlsafe(16),
        **claims,
    }
    keys = _signing_keys()
    access_token = jwt.encode(access_payload, keys["private_key"], algorithm="RS256", headers={"kid": keys["kid"]})
    id_token = _build_id_token(user=user, client_id=client.client_id, nonce=auth_code.nonce, now=now, exp=id_exp)
    refresh_token_value = secrets.token_urlsafe(48)

    auth_code.consumed_at = now
    db.session.add(
        RefreshToken(
            token=refresh_token_value,
            user_id=user.id,
            client_id=client.client_id,
            scope=auth_code.scope,
            expires_at=refresh_exp,
            revoked=False,
        )
    )
    db.session.commit()
    emit_token_issued(user.id, client.client_id)

    return jsonify(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": int((access_exp - now).total_seconds()),
            "id_token": id_token,
            "refresh_token": refresh_token_value,
            "scope": auth_code.scope,
        }
    )


def _decode_bearer_token(access_token):
    keys = _signing_keys()
    return jwt.decode(
        access_token,
        keys["public_key"],
        algorithms=["RS256"],
        options={"require": ["sub", "exp", "iat", "scope"], "verify_aud": False},
    )


@bp.get("/userinfo")
def userinfo():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return _token_error(401, "invalid_token", "missing bearer token")

    token_value = auth_header.split(" ", 1)[1].strip()
    try:
        payload = _decode_bearer_token(token_value)
    except Exception:
        return _token_error(401, "invalid_token", "invalid bearer token")

    user = db.session.get(User, int(payload["sub"]))
    if not user:
        return _token_error(401, "invalid_token", "user no longer exists")

    return jsonify(_claims_for_user(user))


def _require_admin_user():
    """Return the current user if they are an admin, otherwise an error response tuple."""
    user = _current_user()
    if user is None:
        return None, (jsonify({"error": "unauthenticated", "error_description": "Admin login required"}), 401)
    if not user.is_admin:
        return None, (jsonify({"error": "forbidden", "error_description": "Admin access required"}), 403)
    return user, None


def _serialize_user(user, include_counts=False):
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_admin": bool(user.is_admin),
        "timezone_name": user.timezone_name,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }
    if include_counts:
        data["active_sessions"] = Session.query.filter(
            Session.user_id == user.id, Session.expires_at > _utcnow()
        ).count()
    return data


def _paginate(query, page, per_page):
    page = max(1, int(page))
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return items, total, page


@bp.get("/admin/users")
def admin_list_users():
    _, err = _require_admin_user()
    if err is not None:
        return err

    query = (request.args.get("q") or "").strip()
    page = request.args.get("page", 1)
    per_page = 25

    stmt = User.query
    if query:
        like = f"%{query}%"
        stmt = stmt.filter((User.username.ilike(like)) | (User.email.ilike(like)))
    stmt = stmt.order_by(User.created_at.desc())

    users, total, page = _paginate(stmt, page, per_page)
    return jsonify(
        {
            "users": [_serialize_user(u, include_counts=True) for u in users],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": max(1, (total + per_page - 1) // per_page),
        }
    )


@bp.get("/admin/users/<int:user_id>")
def admin_user_detail(user_id):
    _, err = _require_admin_user()
    if err is not None:
        return err

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not_found", "error_description": "User not found"}), 404

    sessions = (
        Session.query.filter_by(user_id=user.id).order_by(Session.created_at.desc()).limit(20).all()
    )
    refresh_tokens = (
        RefreshToken.query.filter_by(user_id=user.id).order_by(RefreshToken.created_at.desc()).limit(20).all()
    )
    codes = (
        AuthorizationCode.query.filter_by(user_id=user.id)
        .order_by(AuthorizationCode.created_at.desc())
        .limit(20)
        .all()
    )

    return jsonify(
        {
            "user": _serialize_user(user, include_counts=True),
            "sessions": [
                {
                    "id": s.id,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "expires_at": s.expires_at.isoformat() if s.expires_at else None,
                    "is_active": s.expires_at > _utcnow() if s.expires_at else False,
                }
                for s in sessions
            ],
            "refresh_tokens": [
                {
                    "id": t.id,
                    "client_id": t.client_id,
                    "scope": t.scope,
                    "revoked": bool(t.revoked),
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                }
                for t in refresh_tokens
            ],
            "authorization_codes": [
                {
                    "id": c.id,
                    "client_id": c.client_id,
                    "scope": c.scope,
                    "consumed_at": c.consumed_at.isoformat() if c.consumed_at else None,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in codes
            ],
        }
    )


@bp.post("/admin/users/<int:user_id>/role")
def admin_set_user_role(user_id):
    _, err = _require_admin_user()
    if err is not None:
        return err

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not_found", "error_description": "User not found"}), 404

    payload = request.get_json(silent=True) or {}
    user.is_admin = bool(payload.get("is_admin", user.is_admin))
    db.session.commit()
    return jsonify(_serialize_user(user))


@bp.post("/admin/users/<int:user_id>/reset-password")
def admin_reset_password(user_id):
    _, err = _require_admin_user()
    if err is not None:
        return err

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not_found", "error_description": "User not found"}), 404

    payload = request.get_json(silent=True) or {}
    new_password = _clean_value(payload.get("password", ""))
    if len(new_password) < 8:
        return jsonify({"error": "invalid_password", "error_description": "Password must be at least 8 characters."}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"id": user.id, "reset": True})


@bp.post("/admin/users/<int:user_id>/revoke-sessions")
def admin_revoke_sessions(user_id):
    _, err = _require_admin_user()
    if err is not None:
        return err

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not_found", "error_description": "User not found"}), 404

    deleted = Session.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({"id": user.id, "revoked_sessions": deleted})


@bp.delete("/admin/users/<int:user_id>")
def admin_delete_user(user_id):
    admin, err = _require_admin_user()
    if err is not None:
        return err

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "not_found", "error_description": "User not found"}), 404

    if user.id == admin.id:
        return jsonify({"error": "self_delete", "error_description": "You cannot delete your own account."}), 400

    Session.query.filter_by(user_id=user.id).delete()
    RefreshToken.query.filter_by(user_id=user.id).delete()
    AuthorizationCode.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"deleted": user.id})


@bp.get("/admin/logs")
def admin_logs():
    _, err = _require_admin_user()
    if err is not None:
        return err

    limit = 60
    sessions = Session.query.order_by(Session.created_at.desc()).limit(limit).all()
    codes = AuthorizationCode.query.order_by(AuthorizationCode.created_at.desc()).limit(limit).all()
    tokens = RefreshToken.query.order_by(RefreshToken.created_at.desc()).limit(limit).all()
    clients = OauthClient.query.order_by(OauthClient.created_at.desc()).all()

    user_map = {u.id: u.username for u in User.query.all()}

    def _entry(kind, ts, username, detail):
        return {
            "kind": kind,
            "timestamp": ts.isoformat() if ts else None,
            "username": username,
            "detail": detail,
        }

    entries = []
    for s in sessions:
        entries.append(_entry("session", s.created_at, user_map.get(s.user_id, "unknown"), "Signed in (new session created)"))
    for c in codes:
        entries.append(_entry("authorization", c.created_at, user_map.get(c.user_id, "unknown"), f"Authorized client {c.client_id} ({c.scope})"))
    for t in tokens:
        state = "revoked" if t.revoked else "issued"
        entries.append(_entry("token", t.created_at, user_map.get(t.user_id, "unknown"), f"Refresh token {state} for {t.client_id}"))

    entries.sort(key=lambda e: (e["timestamp"] or ""), reverse=True)
    entries = entries[:limit]

    return jsonify(
        {
            "activity": entries,
            "clients": [
                {
                    "client_id": c.client_id,
                    "scope": c.scope,
                    "is_confidential": bool(c.is_confidential),
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                }
                for c in clients
            ],
            "stats": {
                "users": User.query.count(),
                "active_sessions": Session.query.filter(Session.expires_at > _utcnow()).count(),
                "oauth_clients": OauthClient.query.count(),
            },
        }
    )
