"""
Usage analytics capture for NoteStack.

Records (legal) product usage events so admins can view, manage, and download
patterns from the per-app admin dashboard. Only operational behaviour is
captured: feature/page usage, actor (user_id), timestamp, client IP, and user
agent. Note contents and secrets are never written here.

Wire into the app with ``init_usage_tracking(app)`` from the app factory. Most
requests are auto-classified via an ``after_request`` hook; authentication events
that happen before ``g.user_id`` is populated are recorded explicitly by the auth
routes using :func:`record_event`.
"""
from __future__ import annotations

import json
from typing import Optional

from flask import Request, Response, g, request

from .database import record_usage_event

# Friendly event-type names keyed by Flask endpoint.
_MAIN_PAGE_MAP = {
    "main.index": "page_home",
    "main.app_view": "page_app",
    "main.settings_view": "page_settings",
    "main.admin_view": "page_admin",
    "main.sync_log_view": "page_sync_log",
    "main.admin_usage_view": "page_usage",
    "main.admin_usage_export": "usage_export",
    "main.admin_usage_delete_event": "usage_event_delete",
    "main.admin_usage_clear": "usage_clear",
}

_API_MAP = {
    "post_note": "note_create",
    "put_note": "note_update",
    "del_note": "note_delete",
    "list_notes": "note_list",
    "get_single_note": "note_view",
    "post_folder": "folder_create",
    "put_folder": "folder_update",
    "del_folder": "folder_delete",
    "post_tag": "tag_create",
    "put_tag": "tag_update",
    "del_tag": "tag_delete",
    "sync_push": "sync_push",
    "sync_pull": "sync_pull",
    "sync_push_folders": "sync_push_folders",
    "sync_pull_folders": "sync_pull_folders",
    "sync_push_tags": "sync_push_tags",
    "sync_push_note_tombstones": "sync_push_note_tombstones",
    "sync_push_folder_tombstones": "sync_push_folder_tombstones",
    "sync_push_tag_tombstones": "sync_push_tag_tombstones",
    "export_backup": "backup_export",
    "import_backup": "backup_import",
    "delete_all_data": "data_delete",
    "generate_token": "token_create",
    "revoke_token": "token_revoke",
    "update_timezone": "timezone_update",
    "usage_export": "usage_export",
}

# Auth events are recorded explicitly by the auth routes (user_id is not yet on
# ``g`` during those requests), so the auto hook must ignore them. Management
# mutations on the analytics store itself are excluded to avoid self-referential
# events (a cleared/deleted row would otherwise spawn a new one).
_SKIP_PREFIXES = ("auth.",)
_SKIP_ENDPOINTS = {
    "main.admin_usage_delete_event",
    "main.admin_usage_clear",
}


def _client_ip(req: Request) -> Optional[str]:
    forwarded = (req.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = (req.headers.get("X-Real-IP") or "").strip()
    if real_ip:
        return real_ip
    return req.remote_addr


def _classify(endpoint: Optional[str], method: str, path: str) -> Optional[str]:
    if not endpoint:
        return None
    if endpoint == "static" or path.startswith("/static"):
        return None
    if endpoint in _SKIP_ENDPOINTS:
        return None
    if endpoint.startswith(_SKIP_PREFIXES):
        return None
    if endpoint.startswith("main."):
        return _MAIN_PAGE_MAP.get(endpoint, f"page_{endpoint[len('main.'):]}")
    if endpoint.startswith("api."):
        name = endpoint[len("api."):]
        return _API_MAP.get(name, f"api_{method.lower()}_{name}")
    return f"route_{method.lower()}_{endpoint}"


def record_event(event_type: str, detail: Optional[dict] = None, user_id: Optional[int] = None) -> None:
    """Record a usage event using the current request for client metadata."""
    try:
        detail_json = json.dumps(detail, default=str) if detail else None
        record_usage_event(
            user_id=user_id if user_id is not None else g.get("user_id"),
            event_type=event_type,
            event_detail=detail_json,
            ip_address=_client_ip(request),
            user_agent=(request.user_agent.string if request.user_agent else None),
        )
    except Exception:
        # Usage capture must never break the request path.
        pass


def init_usage_tracking(app) -> None:
    @app.after_request
    def _capture_usage(response: Response) -> Response:
        try:
            endpoint = request.endpoint
            event_type = _classify(endpoint, request.method, request.path)
            if not event_type:
                return response
            detail = {
                "path": request.path,
                "method": request.method,
                "endpoint": endpoint,
            }
            record_usage_event(
                user_id=g.get("user_id"),
                event_type=event_type,
                event_detail=json.dumps(detail, default=str),
                ip_address=_client_ip(request),
                user_agent=(request.user_agent.string if request.user_agent else None),
                status_code=response.status_code,
            )
        except Exception:
            pass
        return response
