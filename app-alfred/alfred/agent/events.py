"""Run event streaming helpers (powers the polling live UI)."""

from __future__ import annotations

import json

from ..extensions import db
from ..models import RunEvent


def emit_event(run_id: str, user_id: str, event_type: str, payload: dict, seq: int | None = None):
    if seq is None:
        last = (
            RunEvent.query.filter_by(run_id=run_id).order_by(RunEvent.seq.desc()).first()
        )
        seq = (last.seq + 1) if last else 0
    event = RunEvent(
        run_id=run_id,
        user_id=user_id,
        seq=seq,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str),
    )
    db.session.add(event)
    db.session.commit()
    return event


def get_events(run_id: str, user_id: str, after_seq: int = -1):
    rows = (
        RunEvent.query.filter_by(run_id=run_id, user_id=user_id)
        .filter(RunEvent.seq > after_seq)
        .order_by(RunEvent.seq.asc())
        .all()
    )
    return [
        {"seq": e.seq, "type": e.event_type, "payload": e.payload, "created_at": e.created_at.isoformat()}
        for e in rows
    ]


EVT_PLAN = "plan"
EVT_LLM_THINK = "llm_think"
EVT_LLM_MESSAGE = "llm_message"
EVT_TOOL_CALL = "tool_call"
EVT_TOOL_RESULT = "tool_result"
EVT_ARTIFACT = "artifact"
EVT_STATUS = "status"
EVT_ERROR = "error"
