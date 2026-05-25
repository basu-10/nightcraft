from datetime import datetime
from pathlib import Path
from uuid import uuid4

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import AgentRun, ChatSession, ConnectionProfile, Message, Note, Notification, Project, RunEvent, SessionFile, Workspace
from ..settings import (
    get_user_provider_presets,
    get_user_workspace_settings,
    get_user_tool_policies,
    get_user_tool_settings,
    save_user_provider_presets,
    save_user_workspace_settings_patch,
    save_user_tool_policies,
    save_user_tool_settings,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")

_ALLOWED_PROVIDERS = {"lm_studio", "ollama", "openrouter", "advanced"}
_ALLOWED_ROLES = {
    "agent",
    "agent_fallback",
    "code",
    "code_fallback",
    "summarization",
    "summarization_fallback",
}
_ALLOWED_RUN_STATUSES = {"queued", "running", "done", "error"}


def _is_managed_preset_profile(row: ConnectionProfile) -> bool:
    settings = row.settings or {}
    return bool(settings.get("_preset_managed")) and bool(settings.get("_preset_id"))


def _upsert_profile_from_preset(user_id: str, preset: dict) -> ConnectionProfile | None:
    if not isinstance(preset, dict):
        return None
    preset_id = (preset.get("id") or "").strip()
    provider = (preset.get("provider") or "").strip()
    settings = preset.get("settings") or {}
    name = (preset.get("name") or "").strip()
    if not preset_id or not name:
        return None

    ok, _ = _validate_provider_settings(provider, settings)
    if not ok:
        return None

    managed_profile = None
    rows = ConnectionProfile.query.filter_by(user_id=user_id).all()
    for row in rows:
        row_settings = row.settings or {}
        if row_settings.get("_preset_managed") and row_settings.get("_preset_id") == preset_id:
            managed_profile = row
            break

    next_settings = dict(settings)
    next_settings["_preset_managed"] = True
    next_settings["_preset_id"] = preset_id

    if managed_profile is None:
        managed_profile = ConnectionProfile(
            user_id=user_id,
            name=f"Preset: {name}",
            provider=provider,
            is_active=False,
            settings=next_settings,
        )
        db.session.add(managed_profile)
    else:
        managed_profile.name = f"Preset: {name}"
        managed_profile.provider = provider
        managed_profile.settings = next_settings

    return managed_profile


def _delete_managed_profile_for_preset(user_id: str, preset_id: str) -> None:
    if not preset_id:
        return
    rows = ConnectionProfile.query.filter_by(user_id=user_id).all()
    target = None
    for row in rows:
        settings = row.settings or {}
        if settings.get("_preset_managed") and settings.get("_preset_id") == preset_id:
            target = row
            break
    if target is None:
        return

    for workspace in Workspace.query.filter_by(user_id=user_id, profile_id=target.id).all():
        workspace.profile_id = None
    db.session.delete(target)


def _sync_provider_presets_to_profiles(user_id: str) -> None:
    presets = get_user_provider_presets(user_id)
    preset_ids = {
        (preset.get("id") or "").strip()
        for preset in presets if isinstance(preset, dict)
    }
    for preset in presets:
        _upsert_profile_from_preset(user_id, preset)

    rows = ConnectionProfile.query.filter_by(user_id=user_id).all()
    for row in rows:
        settings = row.settings or {}
        if settings.get("_preset_managed") and settings.get("_preset_id") not in preset_ids:
            for workspace in Workspace.query.filter_by(user_id=user_id, profile_id=row.id).all():
                workspace.profile_id = None
            db.session.delete(row)


def _normalize_provider_preset(payload: dict) -> tuple[dict | None, str]:
    name = (payload.get("name") or "").strip()
    provider = (payload.get("provider") or "").strip()
    model = (payload.get("model") or "").strip()
    settings = payload.get("settings") or {}
    if not name:
        return None, "Preset name is required."
    if provider not in _ALLOWED_PROVIDERS:
        return None, "Invalid provider."
    ok, reason = _validate_provider_settings(provider, settings)
    if not ok:
        return None, reason

    if provider == "advanced":
        if not model:
            model = ((settings.get("agent") or {}).get("model") or "").strip()
    elif not model:
        return None, "Preset model is required."

    return {
        "id": payload.get("id") or str(uuid4()),
        "name": name,
        "provider": provider,
        "model": model,
        "settings": settings,
        "updated_at": datetime.utcnow().isoformat(),
    }, ""


def _normalize_tool_policy(payload: dict) -> tuple[dict | None, str]:
    name = (payload.get("name") or "").strip()
    hard_caps = payload.get("hard_caps") or {}
    try:
        warning_threshold = int(payload.get("warning_threshold", 80))
    except (TypeError, ValueError):
        return None, "warning_threshold must be an integer."
    if not name:
        return None, "Policy name is required."
    if not isinstance(hard_caps, dict):
        return None, "hard_caps must be a JSON object."
    if warning_threshold < 1 or warning_threshold > 100:
        return None, "warning_threshold must be between 1 and 100."
    return {
        "id": payload.get("id") or str(uuid4()),
        "name": name,
        "warning_threshold": warning_threshold,
        "hard_caps": hard_caps,
        "updated_at": datetime.utcnow().isoformat(),
    }, ""


def _to_workspace_dict(row: Workspace) -> dict:
    settings = get_user_workspace_settings(
        row.user_id,
        row.id,
        fallback_profile_id=row.profile_id,
    )
    return {
        "id": row.id,
        "name": row.name,
        "color": row.color,
        "workspace_type": row.workspace_type,
        "tool_ids": row.tool_ids,
        "profile_id": settings.get("profile_id"),
        "tool_policy_id": settings.get("tool_policy_id"),
        "tool_caps": settings.get("tool_caps") or {},
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_session_dict(row: ChatSession) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "title": row.title,
        "thread_id": row.thread_id,
        "archived": row.archived,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_message_dict(row: Message) -> dict:
    return {
        "id": row.id,
        "chat_session_id": row.chat_session_id,
        "role": row.role,
        "content": row.content,
        "tool_steps": row.tool_steps,
        "metadata_json": row.metadata_json,
        "checkpoint_id": row.checkpoint_id,
        "created_at": row.created_at.isoformat(),
    }


def _to_profile_dict(row: ConnectionProfile) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "provider": row.provider,
        "is_active": row.is_active,
        "settings": row.settings,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_project_dict(row: Project) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "description": row.description,
        "archived": row.archived,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_run_dict(row: AgentRun) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "chat_session_id": row.chat_session_id,
        "run_type": row.run_type,
        "status": row.status,
        "query_text": row.query_text,
        "final_answer": row.final_answer,
        "error_text": row.error_text,
        "metadata_json": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _to_run_event_dict(row: RunEvent) -> dict:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "seq": row.seq,
        "event_type": row.event_type,
        "payload_json": row.payload_json,
        "created_at": row.created_at.isoformat(),
    }


def _to_note_dict(row: Note) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "project_id": row.project_id,
        "chat_session_id": row.chat_session_id,
        "title": row.title,
        "body": row.body,
        "tags": row.tags or [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_notification_dict(row: Notification) -> dict:
    return {
        "id": row.id,
        "type": row.type,
        "title": row.title,
        "message": row.message,
        "read": row.read,
        "metadata_json": row.metadata_json,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _to_session_file_dict(row: SessionFile) -> dict:
    return {
        "id": row.id,
        "chat_session_id": row.chat_session_id,
        "workspace_id": row.workspace_id,
        "name": row.name,
        "kind": row.kind,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "download_url": f"/api/files/{row.id}/download",
    }


def _get_workspace_owned(workspace_id: str) -> Workspace | None:
    return Workspace.query.filter_by(id=workspace_id, user_id=current_user.id).first()


def _get_project_owned(project_id: str) -> Project | None:
    return Project.query.filter_by(id=project_id, user_id=current_user.id).first()


def _get_session_owned(session_id: str) -> ChatSession | None:
    return ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()


def _get_message_owned(message_id: str) -> Message | None:
    return Message.query.filter_by(id=message_id, user_id=current_user.id).first()


def _get_profile_owned(profile_id: str) -> ConnectionProfile | None:
    return ConnectionProfile.query.filter_by(id=profile_id, user_id=current_user.id).first()


def _get_run_owned(run_id: str) -> AgentRun | None:
    return AgentRun.query.filter_by(id=run_id, user_id=current_user.id).first()


def _get_note_owned(note_id: str) -> Note | None:
    return Note.query.filter_by(id=note_id, user_id=current_user.id).first()


def _get_notification_owned(notification_id: str) -> Notification | None:
    return Notification.query.filter_by(id=notification_id, user_id=current_user.id).first()


def _get_session_file_owned(file_id: str) -> SessionFile | None:
    return SessionFile.query.filter_by(id=file_id, user_id=current_user.id).first()


def _get_tool_policy_owned(policy_id: str) -> dict | None:
    if not policy_id:
        return None
    for policy in get_user_tool_policies(current_user.id):
        if policy.get("id") == policy_id:
            return policy
    return None


def _session_storage_dir(session_row: ChatSession) -> Path:
    root = Path(current_app.instance_path) / "files"
    folder = root / session_row.user_id[:8] / session_row.workspace_id[:8] / session_row.id[:8]
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _sync_generated_files(session_row: ChatSession) -> None:
    folder = _session_storage_dir(session_row)
    existing = {
        Path(row.storage_path).resolve(): row
        for row in SessionFile.query.filter_by(user_id=current_user.id, chat_session_id=session_row.id).all()
    }
    created = False
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved in existing:
            continue
        relative = path.relative_to(current_app.instance_path)
        row = SessionFile(
            user_id=current_user.id,
            workspace_id=session_row.workspace_id,
            chat_session_id=session_row.id,
            name=path.name,
            kind="generated",
            storage_path=str(relative).replace("\\", "/"),
            mime_type=None,
            size_bytes=path.stat().st_size,
        )
        db.session.add(row)
        created = True
    if created:
        db.session.commit()


def _validate_provider_settings(provider: str, settings: dict) -> tuple[bool, str]:
    if provider not in _ALLOWED_PROVIDERS:
        return False, "Invalid provider."
    if not isinstance(settings, dict):
        return False, "Settings must be a JSON object."

    if provider == "advanced":
        for role in _ALLOWED_ROLES:
            role_cfg = settings.get(role)
            if role_cfg is None:
                continue
            if not isinstance(role_cfg, dict):
                return False, f"{role} must be an object."
            role_provider = role_cfg.get("provider")
            if role_provider not in {"lm_studio", "ollama", "openrouter"}:
                return False, f"{role}.provider must be lm_studio, ollama, or openrouter."
            model = role_cfg.get("model", "")
            if model is not None and not isinstance(model, str):
                return False, f"{role}.model must be a string."
        shared_key = settings.get("or_api_key", "")
        if shared_key is not None and not isinstance(shared_key, str):
            return False, "or_api_key must be a string."
        return True, ""

    if provider == "openrouter":
        api_key = settings.get("api_key", "")
        if api_key is not None and not isinstance(api_key, str):
            return False, "api_key must be a string."
        return True, ""

    api_base = settings.get("api_base", "")
    if api_base is not None and not isinstance(api_base, str):
        return False, "api_base must be a string."
    return True, ""


def _next_event_seq(run_id: str) -> int:
    row = (
        db.session.query(db.func.max(RunEvent.seq))
        .filter(RunEvent.run_id == run_id)
        .scalar()
    )
    return int(row or 0) + 1


def _append_run_event(run_id: str, event_type: str, payload_json: dict | None = None) -> RunEvent:
    event = RunEvent(
        run_id=run_id,
        user_id=current_user.id,
        seq=_next_event_seq(run_id),
        event_type=event_type,
        payload_json=payload_json or {},
    )
    db.session.add(event)
    return event


@api_bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@api_bp.get("/workspaces")
@login_required
def list_workspaces():
    rows = (
        Workspace.query
        .filter_by(user_id=current_user.id)
        .order_by(Workspace.created_at.asc())
        .all()
    )
    return jsonify([_to_workspace_dict(row) for row in rows]), 200


@api_bp.post("/workspaces")
@login_required
def create_workspace():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Workspace name is required."}), 400

    workspace_type = (payload.get("workspace_type") or "react").strip().lower()
    if workspace_type not in {"react", "standard"}:
        workspace_type = "react"

    tool_ids = payload.get("tool_ids") or []
    if not isinstance(tool_ids, list):
        return jsonify({"error": "tool_ids must be an array."}), 400

    workspace = Workspace(
        user_id=current_user.id,
        name=name,
        color=(payload.get("color") or "#4A90D9").strip(),
        workspace_type=workspace_type,
        tool_ids=tool_ids,
    )

    profile_id = payload.get("profile_id")
    if profile_id:
        profile = _get_profile_owned(profile_id)
        if not profile:
            return jsonify({"error": "profile_id does not belong to current user."}), 400
        workspace.profile_id = profile.id

    db.session.add(workspace)
    db.session.commit()
    return jsonify(_to_workspace_dict(workspace)), 201


@api_bp.get("/workspaces/<workspace_id>")
@login_required
def get_workspace(workspace_id: str):
    row = _get_workspace_owned(workspace_id)
    if not row:
        return jsonify({"error": "Workspace not found."}), 404
    return jsonify(_to_workspace_dict(row)), 200


@api_bp.get("/workspaces/<workspace_id>/settings")
@login_required
def get_workspace_settings(workspace_id: str):
    row = _get_workspace_owned(workspace_id)
    if not row:
        return jsonify({"error": "Workspace not found."}), 404
    settings = get_user_workspace_settings(
        current_user.id,
        row.id,
        fallback_profile_id=row.profile_id,
    )
    return jsonify(settings), 200


@api_bp.patch("/workspaces/<workspace_id>/settings")
@login_required
def update_workspace_settings(workspace_id: str):
    row = _get_workspace_owned(workspace_id)
    if not row:
        return jsonify({"error": "Workspace not found."}), 404

    payload = request.get_json(silent=True) or {}
    patch: dict = {}

    if "profile_id" in payload:
        profile_id = payload.get("profile_id")
        if profile_id in (None, ""):
            row.profile_id = None
            patch["profile_id"] = None
        else:
            profile = _get_profile_owned(profile_id)
            if not profile:
                return jsonify({"error": "profile_id does not belong to current user."}), 400
            row.profile_id = profile.id
            patch["profile_id"] = profile.id

    if "tool_policy_id" in payload:
        tool_policy_id = payload.get("tool_policy_id")
        if tool_policy_id in (None, ""):
            patch["tool_policy_id"] = None
        else:
            policy = _get_tool_policy_owned(tool_policy_id)
            if not policy:
                return jsonify({"error": "tool_policy_id does not belong to current user."}), 400
            patch["tool_policy_id"] = tool_policy_id
            if "tool_caps" not in payload:
                patch["tool_caps"] = policy.get("hard_caps") or {}

    if "tool_caps" in payload:
        tool_caps = payload.get("tool_caps")
        if not isinstance(tool_caps, dict):
            return jsonify({"error": "tool_caps must be a JSON object."}), 400
        patch["tool_caps"] = tool_caps

    db.session.commit()
    settings = save_user_workspace_settings_patch(
        current_user.id,
        row.id,
        patch,
        fallback_profile_id=row.profile_id,
    )
    settings["profile_id"] = row.profile_id
    return jsonify(settings), 200


@api_bp.patch("/workspaces/<workspace_id>")
@login_required
def update_workspace(workspace_id: str):
    row = _get_workspace_owned(workspace_id)
    if not row:
        return jsonify({"error": "Workspace not found."}), 404

    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Workspace name cannot be empty."}), 400
        row.name = name
    if "color" in payload:
        row.color = (payload.get("color") or "#4A90D9").strip()
    if "workspace_type" in payload:
        value = (payload.get("workspace_type") or "").strip().lower()
        if value not in {"react", "standard"}:
            return jsonify({"error": "workspace_type must be react or standard."}), 400
        row.workspace_type = value
    if "tool_ids" in payload:
        tool_ids = payload.get("tool_ids")
        if not isinstance(tool_ids, list):
            return jsonify({"error": "tool_ids must be an array."}), 400
        row.tool_ids = tool_ids
    if "profile_id" in payload:
        profile_id = payload.get("profile_id")
        if profile_id in (None, ""):
            row.profile_id = None
        else:
            profile = _get_profile_owned(profile_id)
            if not profile:
                return jsonify({"error": "profile_id does not belong to current user."}), 400
            row.profile_id = profile.id

    settings_patch: dict = {}
    if "tool_policy_id" in payload:
        tool_policy_id = payload.get("tool_policy_id")
        if tool_policy_id in (None, ""):
            settings_patch["tool_policy_id"] = None
        else:
            policy = _get_tool_policy_owned(tool_policy_id)
            if not policy:
                return jsonify({"error": "tool_policy_id does not belong to current user."}), 400
            settings_patch["tool_policy_id"] = tool_policy_id
            if "tool_caps" not in payload:
                settings_patch["tool_caps"] = policy.get("hard_caps") or {}
    if "tool_caps" in payload:
        tool_caps = payload.get("tool_caps")
        if not isinstance(tool_caps, dict):
            return jsonify({"error": "tool_caps must be a JSON object."}), 400
        settings_patch["tool_caps"] = tool_caps

    db.session.commit()
    if settings_patch or "profile_id" in payload:
        settings_patch["profile_id"] = row.profile_id
        save_user_workspace_settings_patch(
            current_user.id,
            row.id,
            settings_patch,
            fallback_profile_id=row.profile_id,
        )
    return jsonify(_to_workspace_dict(row)), 200


@api_bp.delete("/workspaces/<workspace_id>")
@login_required
def delete_workspace(workspace_id: str):
    row = _get_workspace_owned(workspace_id)
    if not row:
        return jsonify({"error": "Workspace not found."}), 404

    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/workspaces/<workspace_id>/sessions")
@login_required
def list_sessions(workspace_id: str):
    workspace = _get_workspace_owned(workspace_id)
    if not workspace:
        return jsonify({"error": "Workspace not found."}), 404

    rows = (
        ChatSession.query
        .filter_by(user_id=current_user.id, workspace_id=workspace.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return jsonify([_to_session_dict(row) for row in rows]), 200


@api_bp.post("/workspaces/<workspace_id>/sessions")
@login_required
def create_session(workspace_id: str):
    workspace = _get_workspace_owned(workspace_id)
    if not workspace:
        return jsonify({"error": "Workspace not found."}), 404

    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "New Chat").strip() or "New Chat"

    project_id = payload.get("project_id")
    if project_id:
        project = _get_project_owned(project_id)
        if not project or project.workspace_id != workspace.id:
            return jsonify({"error": "project_id not found or does not belong to this workspace."}), 400
    else:
        project_id = None

    row = ChatSession(
        user_id=current_user.id,
        workspace_id=workspace.id,
        title=title,
        project_id=project_id,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_session_dict(row)), 201


@api_bp.get("/sessions/<session_id>")
@login_required
def get_session(session_id: str):
    row = _get_session_owned(session_id)
    if not row:
        return jsonify({"error": "Session not found."}), 404
    return jsonify(_to_session_dict(row)), 200


@api_bp.patch("/sessions/<session_id>")
@login_required
def update_session(session_id: str):
    row = _get_session_owned(session_id)
    if not row:
        return jsonify({"error": "Session not found."}), 404

    payload = request.get_json(silent=True) or {}
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Session title cannot be empty."}), 400
        row.title = title
    if "archived" in payload:
        row.archived = bool(payload.get("archived"))

    db.session.commit()
    return jsonify(_to_session_dict(row)), 200


@api_bp.delete("/sessions/<session_id>")
@login_required
def delete_session(session_id: str):
    row = _get_session_owned(session_id)
    if not row:
        return jsonify({"error": "Session not found."}), 404

    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/sessions/<session_id>/messages")
@login_required
def list_messages(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404

    rows = (
        Message.query
        .filter_by(user_id=current_user.id, chat_session_id=session_row.id)
        .order_by(Message.created_at.asc())
        .all()
    )
    return jsonify([_to_message_dict(row) for row in rows]), 200


@api_bp.post("/sessions/<session_id>/messages")
@login_required
def create_message(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404

    payload = request.get_json(silent=True) or {}
    role = (payload.get("role") or "user").strip().lower()
    content = (payload.get("content") or "").strip()
    if role not in {"user", "assistant", "tool", "system"}:
        return jsonify({"error": "Invalid message role."}), 400
    if not content:
        return jsonify({"error": "Message content is required."}), 400

    row = Message(
        user_id=current_user.id,
        chat_session_id=session_row.id,
        role=role,
        content=content,
        tool_steps=payload.get("tool_steps"),
        metadata_json=payload.get("metadata_json"),
        checkpoint_id=payload.get("checkpoint_id"),
    )
    db.session.add(row)
    session_row.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(_to_message_dict(row)), 201


@api_bp.patch("/messages/<message_id>")
@login_required
def update_message(message_id: str):
    row = _get_message_owned(message_id)
    if not row:
        return jsonify({"error": "Message not found."}), 404

    payload = request.get_json(silent=True) or {}
    if "content" in payload:
        content = (payload.get("content") or "").strip()
        if not content:
            return jsonify({"error": "Message content cannot be empty."}), 400
        row.content = content
    if "tool_steps" in payload:
        row.tool_steps = payload.get("tool_steps")
    if "metadata_json" in payload:
        row.metadata_json = payload.get("metadata_json")

    db.session.commit()
    return jsonify(_to_message_dict(row)), 200


@api_bp.delete("/messages/<message_id>")
@login_required
def delete_message(message_id: str):
    row = _get_message_owned(message_id)
    if not row:
        return jsonify({"error": "Message not found."}), 404

    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/profiles")
@login_required
def list_profiles():
    _sync_provider_presets_to_profiles(current_user.id)
    db.session.commit()
    rows = (
        ConnectionProfile.query
        .filter_by(user_id=current_user.id)
        .order_by(ConnectionProfile.created_at.asc())
        .all()
    )
    return jsonify([_to_profile_dict(row) for row in rows]), 200


@api_bp.post("/profiles")
@login_required
def create_profile():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    provider = (payload.get("provider") or "").strip()
    settings = payload.get("settings") or {}

    if not name:
        return jsonify({"error": "Profile name is required."}), 400

    ok, reason = _validate_provider_settings(provider, settings)
    if not ok:
        return jsonify({"error": reason}), 400

    is_active = bool(payload.get("is_active"))
    if is_active:
        (
            ConnectionProfile.query
            .filter_by(user_id=current_user.id, is_active=True)
            .update({"is_active": False})
        )

    row = ConnectionProfile(
        user_id=current_user.id,
        name=name,
        provider=provider,
        settings=settings,
        is_active=is_active,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_profile_dict(row)), 201


@api_bp.patch("/profiles/<profile_id>")
@login_required
def update_profile(profile_id: str):
    row = _get_profile_owned(profile_id)
    if not row:
        return jsonify({"error": "Profile not found."}), 404

    payload = request.get_json(silent=True) or {}
    provider = (payload.get("provider") or row.provider).strip()
    settings = payload.get("settings", row.settings)

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Profile name cannot be empty."}), 400
        row.name = name

    ok, reason = _validate_provider_settings(provider, settings)
    if not ok:
        return jsonify({"error": reason}), 400

    row.provider = provider
    row.settings = settings

    if "is_active" in payload:
        is_active = bool(payload.get("is_active"))
        if is_active:
            (
                ConnectionProfile.query
                .filter_by(user_id=current_user.id, is_active=True)
                .update({"is_active": False})
            )
        row.is_active = is_active

    db.session.commit()
    return jsonify(_to_profile_dict(row)), 200


@api_bp.post("/profiles/<profile_id>/activate")
@login_required
def activate_profile(profile_id: str):
    row = _get_profile_owned(profile_id)
    if not row:
        return jsonify({"error": "Profile not found."}), 404

    (
        ConnectionProfile.query
        .filter_by(user_id=current_user.id, is_active=True)
        .update({"is_active": False})
    )
    row.is_active = True
    db.session.commit()
    return jsonify(_to_profile_dict(row)), 200


@api_bp.delete("/profiles/<profile_id>")
@login_required
def delete_profile(profile_id: str):
    row = _get_profile_owned(profile_id)
    if not row:
        return jsonify({"error": "Profile not found."}), 404

    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/settings/tools")
@login_required
def get_tool_settings():
    return jsonify(get_user_tool_settings(current_user.id)), 200


@api_bp.patch("/settings/tools")
@login_required
def patch_tool_settings():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"error": "Tool settings payload must be a JSON object."}), 400
    normalized = save_user_tool_settings(current_user.id, payload)
    return jsonify(normalized), 200


@api_bp.get("/settings/provider-presets")
@login_required
def list_provider_presets():
    return jsonify(get_user_provider_presets(current_user.id)), 200


@api_bp.post("/settings/provider-presets")
@login_required
def create_provider_preset():
    payload = request.get_json(silent=True) or {}
    normalized, error = _normalize_provider_preset(payload)
    if not normalized:
        return jsonify({"error": error}), 400
    presets = get_user_provider_presets(current_user.id)
    presets.insert(0, normalized)
    save_user_provider_presets(current_user.id, presets)
    _upsert_profile_from_preset(current_user.id, normalized)
    db.session.commit()
    return jsonify(normalized), 201


@api_bp.patch("/settings/provider-presets/<preset_id>")
@login_required
def update_provider_preset(preset_id: str):
    payload = request.get_json(silent=True) or {}
    payload["id"] = preset_id
    normalized, error = _normalize_provider_preset(payload)
    if not normalized:
        return jsonify({"error": error}), 400
    presets = get_user_provider_presets(current_user.id)
    updated = False
    next_presets = []
    for preset in presets:
        if preset.get("id") == preset_id:
            next_presets.append(normalized)
            updated = True
        else:
            next_presets.append(preset)
    if not updated:
        return jsonify({"error": "Provider preset not found."}), 404
    save_user_provider_presets(current_user.id, next_presets)
    _upsert_profile_from_preset(current_user.id, normalized)
    db.session.commit()
    return jsonify(normalized), 200


@api_bp.delete("/settings/provider-presets/<preset_id>")
@login_required
def delete_provider_preset(preset_id: str):
    presets = get_user_provider_presets(current_user.id)
    next_presets = [preset for preset in presets if preset.get("id") != preset_id]
    if len(next_presets) == len(presets):
        return jsonify({"error": "Provider preset not found."}), 404
    save_user_provider_presets(current_user.id, next_presets)
    _delete_managed_profile_for_preset(current_user.id, preset_id)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/settings/tool-policies")
@login_required
def list_tool_policies():
    return jsonify(get_user_tool_policies(current_user.id)), 200


@api_bp.post("/settings/tool-policies")
@login_required
def create_tool_policy():
    payload = request.get_json(silent=True) or {}
    normalized, error = _normalize_tool_policy(payload)
    if not normalized:
        return jsonify({"error": error}), 400
    policies = get_user_tool_policies(current_user.id)
    policies.insert(0, normalized)
    save_user_tool_policies(current_user.id, policies)
    return jsonify(normalized), 201


@api_bp.patch("/settings/tool-policies/<policy_id>")
@login_required
def update_tool_policy(policy_id: str):
    payload = request.get_json(silent=True) or {}
    payload["id"] = policy_id
    normalized, error = _normalize_tool_policy(payload)
    if not normalized:
        return jsonify({"error": error}), 400
    policies = get_user_tool_policies(current_user.id)
    updated = False
    next_policies = []
    for policy in policies:
        if policy.get("id") == policy_id:
            next_policies.append(normalized)
            updated = True
        else:
            next_policies.append(policy)
    if not updated:
        return jsonify({"error": "Tool policy not found."}), 404
    save_user_tool_policies(current_user.id, next_policies)
    return jsonify(normalized), 200


@api_bp.delete("/settings/tool-policies/<policy_id>")
@login_required
def delete_tool_policy(policy_id: str):
    policies = get_user_tool_policies(current_user.id)
    next_policies = [policy for policy in policies if policy.get("id") != policy_id]
    if len(next_policies) == len(policies):
        return jsonify({"error": "Tool policy not found."}), 404
    save_user_tool_policies(current_user.id, next_policies)
    return jsonify({"ok": True}), 200


@api_bp.get("/notes")
@login_required
def list_notes():
    query = Note.query.filter_by(user_id=current_user.id)
    workspace_id = request.args.get("workspace_id", "").strip()
    project_id = request.args.get("project_id", "").strip()
    session_id = request.args.get("session_id", "").strip()
    if workspace_id:
        query = query.filter_by(workspace_id=workspace_id)
    if project_id:
        query = query.filter_by(project_id=project_id)
    if session_id:
        query = query.filter_by(chat_session_id=session_id)
    rows = query.order_by(Note.updated_at.desc()).all()
    return jsonify([_to_note_dict(row) for row in rows]), 200


@api_bp.post("/notes")
@login_required
def create_note():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Note title is required."}), 400

    workspace_id = payload.get("workspace_id") or None
    project_id = payload.get("project_id") or None
    chat_session_id = payload.get("chat_session_id") or None

    if workspace_id and not _get_workspace_owned(workspace_id):
        return jsonify({"error": "Workspace not found."}), 404
    if project_id and not _get_project_owned(project_id):
        return jsonify({"error": "Project not found."}), 404
    if chat_session_id and not _get_session_owned(chat_session_id):
        return jsonify({"error": "Session not found."}), 404

    row = Note(
        user_id=current_user.id,
        workspace_id=workspace_id,
        project_id=project_id,
        chat_session_id=chat_session_id,
        title=title,
        body=(payload.get("body") or "").strip(),
        tags=payload.get("tags") if isinstance(payload.get("tags"), list) else [],
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_note_dict(row)), 201


@api_bp.patch("/notes/<note_id>")
@login_required
def update_note(note_id: str):
    row = _get_note_owned(note_id)
    if not row:
        return jsonify({"error": "Note not found."}), 404
    payload = request.get_json(silent=True) or {}
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Note title cannot be empty."}), 400
        row.title = title
    if "body" in payload:
        row.body = (payload.get("body") or "").strip()
    if "tags" in payload:
        row.tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
    db.session.commit()
    return jsonify(_to_note_dict(row)), 200


@api_bp.delete("/notes/<note_id>")
@login_required
def delete_note(note_id: str):
    row = _get_note_owned(note_id)
    if not row:
        return jsonify({"error": "Note not found."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/notifications")
@login_required
def list_notifications():
    rows = (
        Notification.query
        .filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )
    return jsonify([_to_notification_dict(row) for row in rows]), 200


@api_bp.post("/notifications")
@login_required
def create_notification():
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Notification title is required."}), 400
    row = Notification(
        user_id=current_user.id,
        type=(payload.get("type") or "system").strip() or "system",
        title=title,
        message=(payload.get("message") or "").strip(),
        read=bool(payload.get("read")),
        metadata_json=payload.get("metadata_json") if isinstance(payload.get("metadata_json"), dict) else None,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_notification_dict(row)), 201


@api_bp.patch("/notifications/<notification_id>")
@login_required
def update_notification(notification_id: str):
    row = _get_notification_owned(notification_id)
    if not row:
        return jsonify({"error": "Notification not found."}), 404
    payload = request.get_json(silent=True) or {}
    if "read" in payload:
        row.read = bool(payload.get("read"))
    if "title" in payload:
        title = (payload.get("title") or "").strip()
        if not title:
            return jsonify({"error": "Notification title cannot be empty."}), 400
        row.title = title
    if "message" in payload:
        row.message = (payload.get("message") or "").strip()
    db.session.commit()
    return jsonify(_to_notification_dict(row)), 200


@api_bp.delete("/notifications/<notification_id>")
@login_required
def delete_notification(notification_id: str):
    row = _get_notification_owned(notification_id)
    if not row:
        return jsonify({"error": "Notification not found."}), 404
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.post("/notifications/mark-all-read")
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({"read": True})
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/sessions/<session_id>/files")
@login_required
def list_session_files(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404
    _sync_generated_files(session_row)
    rows = (
        SessionFile.query
        .filter_by(user_id=current_user.id, chat_session_id=session_row.id)
        .order_by(SessionFile.created_at.desc())
        .all()
    )
    return jsonify([_to_session_file_dict(row) for row in rows]), 200


@api_bp.post("/sessions/<session_id>/files")
@login_required
def upload_session_files(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404
    uploads = request.files.getlist("files")
    if not uploads:
        return jsonify({"error": "At least one file is required."}), 400

    folder = _session_storage_dir(session_row)
    created_rows = []
    for upload in uploads:
        original_name = secure_filename(upload.filename or "")
        if not original_name:
            continue
        target_name = f"{uuid4().hex}_{original_name}"
        target_path = folder / target_name
        upload.save(target_path)
        relative = target_path.relative_to(current_app.instance_path)
        row = SessionFile(
            user_id=current_user.id,
            workspace_id=session_row.workspace_id,
            chat_session_id=session_row.id,
            name=original_name,
            kind="uploaded",
            storage_path=str(relative).replace("\\", "/"),
            mime_type=upload.mimetype,
            size_bytes=target_path.stat().st_size,
        )
        db.session.add(row)
        created_rows.append(row)

    if not created_rows:
        return jsonify({"error": "No valid files were provided."}), 400
    db.session.commit()
    return jsonify([_to_session_file_dict(row) for row in created_rows]), 201


@api_bp.get("/files/<file_id>/download")
@login_required
def download_session_file(file_id: str):
    row = _get_session_file_owned(file_id)
    if not row:
        return jsonify({"error": "File not found."}), 404
    path = Path(current_app.instance_path) / row.storage_path
    if not path.exists() or not path.is_file():
        return jsonify({"error": "Stored file is missing."}), 404
    return send_file(path, as_attachment=True, download_name=row.name, mimetype=row.mime_type)


@api_bp.delete("/files/<file_id>")
@login_required
def delete_session_file(file_id: str):
    row = _get_session_file_owned(file_id)
    if not row:
        return jsonify({"error": "File not found."}), 404
    path = Path(current_app.instance_path) / row.storage_path
    if path.exists() and path.is_file():
        path.unlink()
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/sessions/<session_id>/runs")
@login_required
def list_runs(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404

    rows = (
        AgentRun.query
        .filter_by(user_id=current_user.id, chat_session_id=session_row.id)
        .order_by(AgentRun.created_at.desc())
        .all()
    )
    return jsonify([_to_run_dict(row) for row in rows]), 200


@api_bp.post("/sessions/<session_id>/runs")
@login_required
def enqueue_run(session_id: str):
    session_row = _get_session_owned(session_id)
    if not session_row:
        return jsonify({"error": "Session not found."}), 404

    payload = request.get_json(silent=True) or {}
    query_text = (payload.get("query") or "").strip()
    if not query_text:
        return jsonify({"error": "query is required."}), 400

    user_message = Message(
        user_id=current_user.id,
        chat_session_id=session_row.id,
        role="user",
        content=query_text,
    )
    db.session.add(user_message)

    run = AgentRun(
        user_id=current_user.id,
        workspace_id=session_row.workspace_id,
        chat_session_id=session_row.id,
        run_type="react",
        status="queued",
        query_text=query_text,
        metadata_json={"scaffold": True},
    )
    db.session.add(run)
    session_row.updated_at = datetime.utcnow()
    db.session.commit()

    run_id = run.id  # capture before the inner app_context changes the session

    # Return immediately so the frontend can poll for real-time step events.
    # The agent runs in a background thread (safe on Debian; PythonAnywhere
    # users should revert to the old synchronous approach).
    import threading
    from flask import current_app

    def _run_background(app, rid: str) -> None:
        with app.app_context():
            from ..agent.runner import _run_once
            _run_once(app, rid)

    t = threading.Thread(target=_run_background, args=(current_app._get_current_object(), run_id), daemon=True)
    t.start()

    db.session.expire_all()
    run = AgentRun.query.filter_by(id=run_id).first()
    return jsonify(_to_run_dict(run)), 201


@api_bp.get("/runs/<run_id>")
@login_required
def get_run(run_id: str):
    run = _get_run_owned(run_id)
    if not run:
        return jsonify({"error": "Run not found."}), 404
    return jsonify(_to_run_dict(run)), 200


@api_bp.patch("/runs/<run_id>")
@login_required
def update_run(run_id: str):
    run = _get_run_owned(run_id)
    if not run:
        return jsonify({"error": "Run not found."}), 404

    payload = request.get_json(silent=True) or {}

    if "status" in payload:
        status = (payload.get("status") or "").strip().lower()
        if status not in _ALLOWED_RUN_STATUSES:
            return jsonify({"error": "Invalid run status."}), 400
        run.status = status
        if status == "running" and not run.started_at:
            run.started_at = datetime.utcnow()
        if status in {"done", "error"}:
            run.finished_at = datetime.utcnow()

    if "final_answer" in payload:
        run.final_answer = payload.get("final_answer")
    if "error_text" in payload:
        run.error_text = payload.get("error_text")
    if "metadata_json" in payload:
        run.metadata_json = payload.get("metadata_json")

    _append_run_event(
        run.id,
        payload.get("event_type") or "status_update",
        payload.get("event_payload") or {"status": run.status},
    )

    if run.status == "done" and run.final_answer:
        assistant_message = Message(
            user_id=current_user.id,
            chat_session_id=run.chat_session_id,
            role="assistant",
            content=run.final_answer,
            metadata_json={"run_id": run.id},
        )
        db.session.add(assistant_message)

    db.session.commit()
    return jsonify(_to_run_dict(run)), 200


@api_bp.get("/runs/<run_id>/events")
@login_required
def list_run_events(run_id: str):
    run = _get_run_owned(run_id)
    if not run:
        return jsonify({"error": "Run not found."}), 404

    rows = (
        RunEvent.query
        .filter_by(user_id=current_user.id, run_id=run.id)
        .order_by(RunEvent.seq.asc())
        .all()
    )
    return jsonify([_to_run_event_dict(row) for row in rows]), 200


# ---------------------------------------------------------------------------
# Project routes
# ---------------------------------------------------------------------------

@api_bp.get("/workspaces/<workspace_id>/projects")
@login_required
def list_projects(workspace_id: str):
    workspace = _get_workspace_owned(workspace_id)
    if not workspace:
        return jsonify({"error": "Workspace not found."}), 404
    include_archived = request.args.get("archived", "").lower() in ("1", "true")
    query = Project.query.filter_by(user_id=current_user.id, workspace_id=workspace.id)
    if not include_archived:
        query = query.filter_by(archived=False)
    rows = query.order_by(Project.created_at.asc()).all()
    return jsonify([_to_project_dict(r) for r in rows]), 200


@api_bp.post("/workspaces/<workspace_id>/projects")
@login_required
def create_project(workspace_id: str):
    workspace = _get_workspace_owned(workspace_id)
    if not workspace:
        return jsonify({"error": "Workspace not found."}), 404
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Project name is required."}), 400
    row = Project(
        user_id=current_user.id,
        workspace_id=workspace.id,
        name=name,
        description=(payload.get("description") or "").strip() or None,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_project_dict(row)), 201


@api_bp.get("/projects/<project_id>")
@login_required
def get_project(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    return jsonify(_to_project_dict(row)), 200


@api_bp.patch("/projects/<project_id>")
@login_required
def update_project(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Project name cannot be empty."}), 400
        row.name = name
    if "description" in payload:
        row.description = (payload.get("description") or "").strip() or None
    if "archived" in payload:
        row.archived = bool(payload["archived"])
    db.session.commit()
    return jsonify(_to_project_dict(row)), 200


@api_bp.delete("/projects/<project_id>")
@login_required
def delete_project(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    row.archived = True
    db.session.commit()
    return jsonify({"ok": True}), 200


@api_bp.get("/projects/<project_id>/memory")
@login_required
def get_project_memory(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    return jsonify({"memory_text": row.memory_text or ""}), 200


@api_bp.put("/projects/<project_id>/memory")
@login_required
def update_project_memory(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    payload = request.get_json(silent=True) or {}
    row.memory_text = payload.get("memory_text") or None
    db.session.commit()
    return jsonify({"memory_text": row.memory_text or ""}), 200


@api_bp.get("/projects/<project_id>/sessions")
@login_required
def list_project_sessions(project_id: str):
    row = _get_project_owned(project_id)
    if not row:
        return jsonify({"error": "Project not found."}), 404
    sessions = (
        ChatSession.query
        .filter_by(user_id=current_user.id, project_id=row.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return jsonify([_to_session_dict(s) for s in sessions]), 200


@api_bp.post("/projects/<project_id>/sessions")
@login_required
def create_project_session(project_id: str):
    project = _get_project_owned(project_id)
    if not project:
        return jsonify({"error": "Project not found."}), 404
    payload = request.get_json(silent=True) or {}
    title = (payload.get("title") or "New Chat").strip() or "New Chat"
    row = ChatSession(
        user_id=current_user.id,
        workspace_id=project.workspace_id,
        project_id=project.id,
        title=title,
    )
    db.session.add(row)
    db.session.commit()
    return jsonify(_to_session_dict(row)), 201


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

@api_bp.get("/dashboard/stats")
@login_required
def dashboard_stats():
    today = datetime.utcnow().date().isoformat()

    total_runs = AgentRun.query.filter_by(user_id=current_user.id).count()
    runs_today = AgentRun.query.filter(
        AgentRun.user_id == current_user.id,
        db.func.date(AgentRun.created_at) == today,
    ).count()

    workspace_rows = Workspace.query.filter_by(user_id=current_user.id).all()
    workspace_stats = []
    for ws in workspace_rows:
        ws_runs = AgentRun.query.filter_by(user_id=current_user.id, workspace_id=ws.id).count()
        ws_sessions = ChatSession.query.filter_by(user_id=current_user.id, workspace_id=ws.id).count()
        workspace_stats.append({
            "id": ws.id,
            "name": ws.name,
            "color": ws.color,
            "run_count": ws_runs,
            "session_count": ws_sessions,
        })

    # Tool call counts from run events with node=tool_executor
    tool_events = (
        RunEvent.query
        .filter_by(user_id=current_user.id, event_type="step")
        .all()
    )
    tool_counts: dict[str, int] = {}
    for ev in tool_events:
        payload = ev.payload_json or {}
        if payload.get("node") == "tool_executor":
            tool_name = payload.get("tool_name") or "unknown"
            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

    return jsonify({
        "total_runs": total_runs,
        "runs_today": runs_today,
        "workspace_stats": workspace_stats,
        "tool_counts": tool_counts,
    }), 200