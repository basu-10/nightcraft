from __future__ import annotations

import json
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.parse import quote, urlsplit

from flask import Blueprint, current_app, g, redirect, request, session, url_for

from ..database import upsert_sso_user
from ..usage_tracking import record_event

auth_bp = Blueprint("auth", __name__)


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


def _auth_service_url(path: str) -> str:
    auth_base = (current_app.config.get("AUTH_SERVICE_URL", "") or "").strip().rstrip("/")
    return f"{auth_base}{path}" if auth_base else path


def _session_me_url() -> str:
    configured = (current_app.config.get("AUTH_SESSION_ME_URL", "") or "").strip()
    if configured:
        return configured
    return _auth_service_url("/session/me")


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

    claims = payload.get("user") or {}
    return claims if isinstance(claims, dict) else None


def ensure_session_from_shared_auth() -> None:
    if session.get("user_id"):
        return

    claims = _claims_from_shared_session()
    if not claims:
        return

    user = upsert_sso_user(claims)
    if user is None:
        return

    session["user_id"] = int(user["id"])
    g.user_id = int(user["id"])
    record_event("auth_login", {"username": user.get("username"), "sso": True}, int(user["id"]))


@auth_bp.route("/login")
def login():
    next_target = _normalize_next_target(request.args.get("next"), url_for("main.app_view"))
    return redirect(f"{_auth_service_url('/login')}?next={quote(next_target, safe='')}")


@auth_bp.route("/register")
def register():
    next_target = _normalize_next_target(request.args.get("next"), url_for("main.app_view"))
    return redirect(f"{_auth_service_url('/register')}?next={quote(next_target, safe='')}")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    next_target = _normalize_next_target(request.args.get("next"), url_for("main.index"))
    return redirect(f"{_auth_service_url('/logout')}?next={quote(next_target, safe='')}")