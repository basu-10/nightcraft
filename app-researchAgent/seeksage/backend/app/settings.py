from __future__ import annotations

from copy import deepcopy

from .extensions import db
from .models import UserPreference


_TOOL_SETTINGS_DEFAULTS: dict = {
    "slides": {
        "min_slides": 5,
        "max_slides": 10,
        "img_width": 1280,
        "img_height": 720,
        "model_override": "",
    },
    "web_search": {
        "default_max_results": 4,
        "max_results_limit": 10,
    },
    "news_search": {
        "default_max_results": 8,
        "max_results_limit": 15,
    },
    "arxiv": {
        "default_max_results": 5,
        "max_results_limit": 15,
    },
    "youtube_transcript": {
        "default_max_videos": 3,
        "max_videos_limit": 10,
        "skip_auto_generated": False,
    },
    "react_agent": {
        "max_steps": 5,
    },
}

_PROVIDER_PRESETS_DEFAULTS: list[dict] = []
_TOOL_POLICY_DEFAULTS: list[dict] = []
_WORKSPACE_SETTINGS_KEY = "workspace_settings"


def _merge_tool_settings(base: dict, updates: dict) -> dict:
    merged = {
        key: (value.copy() if isinstance(value, dict) else value)
        for key, value in base.items()
    }
    for section, section_data in (updates or {}).items():
        if section not in merged:
            continue
        if isinstance(merged[section], dict) and isinstance(section_data, dict):
            merged[section].update(section_data)
    return merged


def get_tool_settings_defaults() -> dict:
    return _merge_tool_settings(_TOOL_SETTINGS_DEFAULTS, {})


def _get_user_pref_json(user_id: str, key: str):
    pref = UserPreference.query.filter_by(user_id=user_id, key=key).first()
    return pref.value_json if pref else None


def _save_user_pref_json(user_id: str, key: str, value):
    pref = UserPreference.query.filter_by(user_id=user_id, key=key).first()
    if not pref:
        pref = UserPreference(user_id=user_id, key=key, value_json=value)
        db.session.add(pref)
    else:
        pref.value_json = value
    db.session.commit()
    return value


def get_user_tool_settings(user_id: str) -> dict:
    pref_value = _get_user_pref_json(user_id, "tool_settings")
    if pref_value is None:
        return get_tool_settings_defaults()
    if not isinstance(pref_value, dict):
        return get_tool_settings_defaults()
    return _merge_tool_settings(get_tool_settings_defaults(), pref_value)


def save_user_tool_settings(user_id: str, tool_settings: dict) -> dict:
    normalized = _merge_tool_settings(get_tool_settings_defaults(), tool_settings or {})
    return _save_user_pref_json(user_id, "tool_settings", normalized)


def get_user_provider_presets(user_id: str) -> list[dict]:
    value = _get_user_pref_json(user_id, "provider_presets")
    if not isinstance(value, list):
        return deepcopy(_PROVIDER_PRESETS_DEFAULTS)
    return value


def save_user_provider_presets(user_id: str, presets: list[dict]) -> list[dict]:
    normalized = presets if isinstance(presets, list) else deepcopy(_PROVIDER_PRESETS_DEFAULTS)
    return _save_user_pref_json(user_id, "provider_presets", normalized)


def get_user_tool_policies(user_id: str) -> list[dict]:
    value = _get_user_pref_json(user_id, "tool_policies")
    if not isinstance(value, list):
        return deepcopy(_TOOL_POLICY_DEFAULTS)
    return value


def save_user_tool_policies(user_id: str, policies: list[dict]) -> list[dict]:
    normalized = policies if isinstance(policies, list) else deepcopy(_TOOL_POLICY_DEFAULTS)
    return _save_user_pref_json(user_id, "tool_policies", normalized)


def get_user_react_max_steps(user_id: str) -> int:
    settings = get_user_tool_settings(user_id)
    try:
        return max(1, int(settings.get("react_agent", {}).get("max_steps", 5)))
    except (TypeError, ValueError):
        return 5


def _normalize_workspace_settings(value: dict | None) -> dict:
    value = value if isinstance(value, dict) else {}
    profile_id = value.get("profile_id")
    if profile_id in ("", None):
        profile_id = None
    tool_policy_id = value.get("tool_policy_id")
    if tool_policy_id in ("", None):
        tool_policy_id = None
    tool_caps = value.get("tool_caps")
    if not isinstance(tool_caps, dict):
        tool_caps = {}
    return {
        "profile_id": profile_id,
        "tool_policy_id": tool_policy_id,
        "tool_caps": tool_caps,
    }


def get_user_workspace_settings_map(user_id: str) -> dict[str, dict]:
    raw = _get_user_pref_json(user_id, _WORKSPACE_SETTINGS_KEY)
    if not isinstance(raw, dict):
        return {}
    normalized: dict[str, dict] = {}
    for workspace_id, payload in raw.items():
        if not isinstance(workspace_id, str):
            continue
        normalized[workspace_id] = _normalize_workspace_settings(payload)
    return normalized


def save_user_workspace_settings_map(user_id: str, settings_map: dict[str, dict]) -> dict[str, dict]:
    normalized: dict[str, dict] = {}
    for workspace_id, payload in (settings_map or {}).items():
        if not isinstance(workspace_id, str):
            continue
        normalized[workspace_id] = _normalize_workspace_settings(payload)
    return _save_user_pref_json(user_id, _WORKSPACE_SETTINGS_KEY, normalized)


def get_user_workspace_settings(
    user_id: str,
    workspace_id: str,
    fallback_profile_id: str | None = None,
) -> dict:
    settings_map = get_user_workspace_settings_map(user_id)
    settings = _normalize_workspace_settings(settings_map.get(workspace_id))
    if fallback_profile_id and not settings.get("profile_id"):
        settings["profile_id"] = fallback_profile_id
    return settings


def save_user_workspace_settings_patch(
    user_id: str,
    workspace_id: str,
    patch: dict,
    fallback_profile_id: str | None = None,
) -> dict:
    settings_map = get_user_workspace_settings_map(user_id)
    current = _normalize_workspace_settings(settings_map.get(workspace_id))
    if fallback_profile_id and not current.get("profile_id"):
        current["profile_id"] = fallback_profile_id

    if "profile_id" in patch:
        profile_id = patch.get("profile_id")
        current["profile_id"] = None if profile_id in ("", None) else profile_id
    if "tool_policy_id" in patch:
        tool_policy_id = patch.get("tool_policy_id")
        current["tool_policy_id"] = None if tool_policy_id in ("", None) else tool_policy_id
    if "tool_caps" in patch:
        tool_caps = patch.get("tool_caps")
        current["tool_caps"] = tool_caps if isinstance(tool_caps, dict) else {}

    settings_map[workspace_id] = _normalize_workspace_settings(current)
    save_user_workspace_settings_map(user_id, settings_map)
    return settings_map[workspace_id]
