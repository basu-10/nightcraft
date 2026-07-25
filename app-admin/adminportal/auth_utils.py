"""Shared auth utilities for app-admin."""
from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib import request as urllib_request

from flask import current_app, request


def build_auth_handoff_url(auth_url: str, return_path: str, return_param: str = "next") -> str:
    """Build a login URL that returns the user to a specific path after auth."""
    parts = urlsplit(auth_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[return_param] = return_path
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _session_me_url() -> str:
    configured = (current_app.config.get("AUTH_SESSION_ME_URL", "") or "").strip()
    if not configured:
        return ""
    if configured.startswith("http://") or configured.startswith("https://"):
        return configured
    return f"{request.host_url.rstrip('/')}/{configured.lstrip('/')}"


def fetch_shared_auth_user() -> dict[str, Any] | None:
    if current_app.testing:
        return None
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
    user = payload.get("user") or {}
    if not isinstance(user, dict):
        return None
    username = (user.get("preferred_username") or "").strip()
    if not username:
        username = (user.get("email") or "").split("@", 1)[0].strip()
    if not username:
        username = "User"
    roles = user.get("roles")
    if isinstance(roles, str):
        normalized_roles = {roles.strip().lower()}
    elif isinstance(roles, (list, tuple, set)):
        normalized_roles = {str(role).strip().lower() for role in roles}
    else:
        normalized_roles = set()
    return {
        "username": username,
        "is_admin": "admin" in normalized_roles or bool(user.get("is_admin", False)),
        "sub": user.get("sub"),
    }
