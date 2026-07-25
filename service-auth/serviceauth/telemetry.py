"""Server-side telemetry emission for service-auth."""
from __future__ import annotations

import json
import os
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from flask import current_app, request


TELEMETRY_ENDPOINT = os.getenv("TELEMETRY_ENDPOINT", "/api/telemetry/v1/events")


def _build_absolute_url(endpoint: str) -> str:
    if endpoint.startswith(("http://", "https://")):
        return endpoint
    base = request.host_url.rstrip("/")
    return urljoin(base + "/", endpoint.lstrip("/"))


def _post_events(events: list[dict]) -> None:
    if not events:
        return

    endpoint = current_app.config.get("TELEMETRY_ENDPOINT", TELEMETRY_ENDPOINT)
    if not endpoint or current_app.config.get("TELEMETRY_DISABLED"):
        return

    absolute_url = _build_absolute_url(endpoint)
    payload = json.dumps({"events": events}).encode("utf-8")
    req = Request(
        absolute_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=2) as _resp:
            pass
    except (HTTPError, URLError, OSError, ValueError):
        pass


def emit_auth_event(event_type: str, user_id: int | None, session_id: str, url: str, properties: dict | None = None) -> None:
    event = {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "user_id": user_id,
        "session_id": session_id,
        "url": url,
        "referrer": None,
        "properties": properties or {},
        "device_info": None,
    }
    _post_events([event])


def emit_login(user_id: int, session_id: str) -> None:
    emit_auth_event("session_resumed", user_id, session_id, "/auth/login", {"method": "credentials"})


def emit_register(user_id: int, session_id: str) -> None:
    emit_auth_event("user_first_seen", user_id, session_id, "/auth/register", {"method": "credentials"})
    emit_auth_event("session_start", user_id, session_id, "/auth/register", {"method": "credentials"})


def emit_oauth_login(user_id: int, session_id: str) -> None:
    emit_auth_event("session_resumed", user_id, session_id, "/auth/login/google", {"method": "google_oauth"})


def emit_oauth_register(user_id: int, session_id: str) -> None:
    emit_auth_event("user_first_seen", user_id, session_id, "/auth/login/google", {"method": "google_oauth"})
    emit_auth_event("session_start", user_id, session_id, "/auth/login/google", {"method": "google_oauth"})


def emit_logout(user_id: int | None, session_id: str) -> None:
    emit_auth_event("session_end", user_id, session_id, "/auth/logout", {})


def emit_token_issued(user_id: int, client_id: str) -> None:
    emit_auth_event("api_call", user_id, "", "/auth/oauth/token", {"method": "POST", "status": 200, "client_id": client_id})
