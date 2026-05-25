from __future__ import annotations

import json
from pathlib import Path

from flask import current_app

from ..extensions import db
from ..models import AppSetting, Segment
from ..utils import compute_loop_segment, now_app_timezone

PLAYABLE_SEGMENT_STATUSES = ("queued", "ready", "playing", "played")
BREAKING_STATE_SETTING_KEY = "listener_breaking_state_v1"


def _automation_log_dir() -> Path:
    base_dir = Path(current_app.instance_path) / "automation_logs"
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _breaking_events_file() -> Path:
    return _automation_log_dir() / "breaking_playback.jsonl"


def _read_breaking_state() -> dict:
    setting = AppSetting.query.filter_by(key=BREAKING_STATE_SETTING_KEY).first()
    if not setting or not setting.value:
        return {}

    try:
        payload = json.loads(setting.value)
    except Exception:
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _write_breaking_state(state: dict) -> None:
    serialized = json.dumps(state, ensure_ascii=True)
    setting = AppSetting.query.filter_by(key=BREAKING_STATE_SETTING_KEY).first()
    if setting:
        setting.value = serialized
        setting.encrypted = False
    else:
        db.session.add(AppSetting(key=BREAKING_STATE_SETTING_KEY, value=serialized, encrypted=False))


def _prune_breaking_event_log(path: Path) -> None:
    max_jsonl_lines = int(current_app.config.get("BREAKING_LOG_MAX_JSONL_LINES", 5000))
    if max_jsonl_lines <= 0 or not path.exists():
        return

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_jsonl_lines:
            path.write_text("\n".join(lines[-max_jsonl_lines:]) + "\n", encoding="utf-8")
    except Exception:
        current_app.logger.exception("Failed pruning breaking playback JSONL log")


def log_breaking_event(event_type: str, payload: dict | None = None) -> None:
    event_payload = {
        "event": event_type,
        "timestamp_utc": now_app_timezone().isoformat(),
    }
    if payload:
        event_payload.update(payload)

    log_file = _breaking_events_file()
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_payload, ensure_ascii=True) + "\n")

    _prune_breaking_event_log(log_file)


def list_recent_breaking_events(limit: int = 50) -> list[dict]:
    path = _breaking_events_file()
    if not path.exists() or limit <= 0:
        return []

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    results = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except Exception:
            continue
        if len(results) >= limit:
            break

    return results


def _playable_segments_for_channel(channel_id: int) -> list[Segment]:
    return (
        Segment.query.filter(
            Segment.channel_id == channel_id,
            Segment.status.in_(PLAYABLE_SEGMENT_STATUSES),
        )
        .order_by(Segment.scheduled_at_utc.asc())
        .all()
    )


def _state_for_channel(channel_id: int) -> dict:
    return _read_breaking_state().get(str(channel_id), {})


def get_breaking_segment_ids(channel_id: int) -> set[int]:
    state = _state_for_channel(channel_id)
    if not state or not state.get("active"):
        return set()

    return {int(seg_id) for seg_id in state.get("injected_segment_ids", []) if str(seg_id).isdigit()}


def register_breaking_injection(channel_id: int, new_segment_ids: list[int], source: str) -> dict:
    clean_ids = []
    seen = set()
    for seg_id in new_segment_ids:
        try:
            numeric = int(seg_id)
        except (TypeError, ValueError):
            continue
        if numeric in seen:
            continue
        seen.add(numeric)
        clean_ids.append(numeric)

    if not clean_ids:
        return {"created": False, "reason": "no_segment_ids"}

    all_segments = _playable_segments_for_channel(channel_id)
    old_segments = [seg for seg in all_segments if seg.id not in seen]
    if not old_segments:
        return {"created": False, "reason": "no_existing_queue"}

    current, _, _ = compute_loop_segment(old_segments)
    if not current:
        return {"created": False, "reason": "no_current_segment"}

    state = _read_breaking_state()
    channel_key = str(channel_id)
    channel_state = state.get(channel_key, {})

    if channel_state.get("active"):
        existing_ids = [int(seg_id) for seg_id in channel_state.get("injected_segment_ids", []) if str(seg_id).isdigit()]
        for seg_id in clean_ids:
            if seg_id not in existing_ids:
                existing_ids.append(seg_id)
        channel_state["injected_segment_ids"] = existing_ids
        channel_state["last_updated_utc"] = now_app_timezone().isoformat()
        channel_state["source"] = source
        event_type = "breaking_extended"
        created = False
    else:
        channel_state = {
            "active": True,
            "anchor_segment_id": current.id,
            "injected_segment_ids": clean_ids,
            "activated_at_utc": now_app_timezone().isoformat(),
            "started_injected_cycle": False,
            "source": source,
        }
        event_type = "breaking_activated"
        created = True

    state[channel_key] = channel_state
    _write_breaking_state(state)
    db.session.commit()

    log_breaking_event(
        event_type,
        {
            "channel_id": channel_id,
            "source": source,
            "anchor_segment_id": channel_state.get("anchor_segment_id"),
            "injected_segment_ids": channel_state.get("injected_segment_ids", []),
        },
    )

    return {
        "created": created,
        "anchor_segment_id": channel_state.get("anchor_segment_id"),
        "injected_segment_ids": channel_state.get("injected_segment_ids", []),
    }


def build_channel_playback_plan(channel_id: int, epoch_seconds=None) -> dict:
    base_playlist = _playable_segments_for_channel(channel_id)
    if not base_playlist:
        return {
            "playlist": [],
            "current_segment": None,
            "playback_offset": 0,
            "loop_total_seconds": 0,
            "breaking_active": False,
            "breaking_segment_ids": set(),
            "breaking_announcement_intro": "",
            "breaking_announcement_resume": "",
        }

    state = _read_breaking_state()
    channel_key = str(channel_id)
    channel_state = state.get(channel_key, {})

    if not channel_state.get("active"):
        current, offset, total = compute_loop_segment(base_playlist, epoch_seconds=epoch_seconds)
        return {
            "playlist": base_playlist,
            "current_segment": current,
            "playback_offset": offset,
            "loop_total_seconds": total,
            "breaking_active": False,
            "breaking_segment_ids": set(),
            "breaking_announcement_intro": "",
            "breaking_announcement_resume": "",
        }

    injected_ids = [int(seg_id) for seg_id in channel_state.get("injected_segment_ids", []) if str(seg_id).isdigit()]
    injected_set = set(injected_ids)

    by_id = {segment.id: segment for segment in base_playlist}
    resolved_injected = [by_id[seg_id] for seg_id in injected_ids if seg_id in by_id]
    old_playlist = [segment for segment in base_playlist if segment.id not in injected_set]
    anchor_id = channel_state.get("anchor_segment_id")

    if not old_playlist or not resolved_injected:
        state.pop(channel_key, None)
        _write_breaking_state(state)
        db.session.commit()
        current_app.logger.warning(
            f"Breaking state cleared for channel {channel_id}: "
            f"old_playlist empty ({not old_playlist}) or injected segments unavailable ({not resolved_injected})"
        )
        log_breaking_event(
            "breaking_state_cleared",
            {
                "channel_id": channel_id,
                "reason": "missing_old_or_injected_segments",
            },
        )
        current, offset, total = compute_loop_segment(base_playlist, epoch_seconds=epoch_seconds)
        return {
            "playlist": base_playlist,
            "current_segment": current,
            "playback_offset": offset,
            "loop_total_seconds": total,
            "breaking_active": False,
            "breaking_segment_ids": set(),
            "breaking_announcement_intro": "",
            "breaking_announcement_resume": "",
        }

    anchor_index = next((index for index, segment in enumerate(old_playlist) if segment.id == anchor_id), -1)
    if anchor_index < 0:
        state.pop(channel_key, None)
        _write_breaking_state(state)
        db.session.commit()
        current_app.logger.warning(
            f"Breaking state cleared for channel {channel_id}: anchor segment {anchor_id} not found in old_playlist "
            f"({len(old_playlist)} segments available)"
        )
        log_breaking_event(
            "breaking_state_cleared",
            {
                "channel_id": channel_id,
                "reason": "anchor_missing",
                "anchor_segment_id": anchor_id,
            },
        )
        current, offset, total = compute_loop_segment(base_playlist, epoch_seconds=epoch_seconds)
        return {
            "playlist": base_playlist,
            "current_segment": current,
            "playback_offset": offset,
            "loop_total_seconds": total,
            "breaking_active": False,
            "breaking_segment_ids": set(),
            "breaking_announcement_intro": "",
            "breaking_announcement_resume": "",
        }

    effective_playlist = old_playlist[: anchor_index + 1] + resolved_injected + old_playlist[anchor_index + 1 :]
    current, offset, total = compute_loop_segment(effective_playlist, epoch_seconds=epoch_seconds)

    prefix_ids = {segment.id for segment in old_playlist[:anchor_index]}
    started = bool(channel_state.get("started_injected_cycle"))

    if current and current.id in injected_set and not started:
        channel_state["started_injected_cycle"] = True
        channel_state["last_updated_utc"] = now_app_timezone().isoformat()
        state[channel_key] = channel_state
        _write_breaking_state(state)
        db.session.commit()
        log_breaking_event(
            "breaking_cycle_started",
            {
                "channel_id": channel_id,
                "anchor_segment_id": anchor_id,
                "current_segment_id": current.id,
            },
        )
        started = True

    if started and current and current.id in prefix_ids:
        state.pop(channel_key, None)
        _write_breaking_state(state)
        db.session.commit()
        log_breaking_event(
            "breaking_cycle_completed",
            {
                "channel_id": channel_id,
                "anchor_segment_id": anchor_id,
                "resume_segment_id": current.id,
            },
        )
        current, offset, total = compute_loop_segment(base_playlist, epoch_seconds=epoch_seconds)
        return {
            "playlist": base_playlist,
            "current_segment": current,
            "playback_offset": offset,
            "loop_total_seconds": total,
            "breaking_active": False,
            "breaking_segment_ids": set(),
            "breaking_announcement_intro": "",
            "breaking_announcement_resume": "",
        }

    return {
        "playlist": effective_playlist,
        "current_segment": current,
        "playback_offset": offset,
        "loop_total_seconds": total,
        "breaking_active": True,
        "breaking_segment_ids": injected_set,
        "breaking_announcement_intro": "New articles coming in. Old articles will be resumed after these breaking articles.",
        "breaking_announcement_resume": "And now resuming the old articles.",
    }
