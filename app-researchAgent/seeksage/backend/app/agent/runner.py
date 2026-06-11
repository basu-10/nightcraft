from __future__ import annotations

from datetime import datetime

from flask import Flask
from langchain_core.messages import SystemMessage

from ..extensions import db
from ..models import AgentRun, ChatSession, Message, Project, RunEvent, Workspace
from ..settings import get_user_react_max_steps
from ..core import activity_log as actlog
from ..core.activity_log import (
    EVT_LLM_CALL,
    EVT_LLM_ERROR,
    EVT_LLM_REPLY,
    EVT_LLM_RETRY,
    EVT_RUN_DONE,
    EVT_RUN_ERROR,
    EVT_RUN_START,
    EVT_TOOL_CACHE_HIT,
    EVT_TOOL_CALL,
    EVT_TOOL_ERROR,
    EVT_TOOL_RETRY,
    EVT_TOOL_RESULT,
    EVT_TOOL_TIMEOUT,
    EVT_USER_MSG,
)
from .citations import append_deterministic_sources
from .graph_react import get_react_graph, resolve_final_answer, to_langchain_messages
from .tools import set_runtime_context


def _next_event_seq(run_id: str) -> int:
    value = db.session.query(db.func.max(RunEvent.seq)).filter(RunEvent.run_id == run_id).scalar()
    return int(value or 0) + 1


def _append_event(run: AgentRun, event_type: str, payload: dict | None = None) -> None:
    db.session.add(
        RunEvent(
            run_id=run.id,
            user_id=run.user_id,
            seq=_next_event_seq(run.id),
            event_type=event_type,
            payload_json=payload or {},
        )
    )


_SEARCH_TOOL_NAMES = {"web_search", "wiki_search", "news_search", "arxiv_search"}


def _format_duration_ms(duration_ms: int | None) -> str:
    if duration_ms is None:
        return "n/a"
    if duration_ms < 1000:
        return "<1s"
    return f"{duration_ms / 1000:.1f}s"


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{name} ({count})" for name, count in sorted(counts.items()))


def _build_usage_stats(run: AgentRun, final_state) -> dict:
    stats = {
        "run_id": run.id,
        "llm_calls": 0,
        "llm_replies": 0,
        "llm_retries": 0,
        "llm_errors": 0,
        "tool_calls": 0,
        "tool_results": 0,
        "tool_cache_hits": 0,
        "tool_retries": 0,
        "tool_timeouts": 0,
        "tool_errors": 0,
        "searches": 0,
        "tool_counts": {},
        "llm_model_counts": {},
        "used_model": "",
        "duration_ms": None,
    }

    events = (
        RunEvent.query
        .filter_by(run_id=run.id)
        .order_by(RunEvent.seq.asc())
        .all()
    )

    for event in events:
        payload = event.payload_json or {}
        event_type = event.event_type

        if event_type == EVT_LLM_CALL:
            stats["llm_calls"] += 1
            model = payload.get("model") or ""
            if model:
                stats["llm_model_counts"][model] = stats["llm_model_counts"].get(model, 0) + 1
        elif event_type == EVT_LLM_REPLY:
            stats["llm_replies"] += 1
        elif event_type == EVT_LLM_RETRY:
            stats["llm_retries"] += 1
        elif event_type == EVT_LLM_ERROR:
            stats["llm_errors"] += 1
        elif event_type == EVT_TOOL_CALL:
            tool = payload.get("tool") or payload.get("tool_name") or ""
            stats["tool_calls"] += 1
            if tool:
                stats["tool_counts"][tool] = stats["tool_counts"].get(tool, 0) + 1
                if tool in _SEARCH_TOOL_NAMES:
                    stats["searches"] += 1
        elif event_type == EVT_TOOL_RESULT:
            stats["tool_results"] += 1
        elif event_type == EVT_TOOL_CACHE_HIT:
            tool = payload.get("tool") or payload.get("tool_name") or ""
            stats["tool_cache_hits"] += 1
            stats["tool_results"] += 1
            if tool:
                stats["tool_counts"][tool] = stats["tool_counts"].get(tool, 0) + 1
                if tool in _SEARCH_TOOL_NAMES:
                    stats["searches"] += 1
        elif event_type == EVT_TOOL_RETRY:
            stats["tool_retries"] += 1
        elif event_type == EVT_TOOL_TIMEOUT:
            stats["tool_timeouts"] += 1
        elif event_type == EVT_TOOL_ERROR:
            stats["tool_errors"] += 1

    if run.started_at and run.finished_at:
        stats["duration_ms"] = int((run.finished_at - run.started_at).total_seconds() * 1000)

    values = (final_state.values or {}) if final_state is not None else {}
    stats["used_model"] = values.get("used_model", "") or ""
    return stats


def _format_usage_stats(stats: dict) -> str:
    lines = [
        "### Usage Stats",
        "",
        f"- **Searches:** {stats.get('searches', 0)}",
        f"- **Tool calls:** {stats.get('tool_calls', 0)}",
        f"- **Tool results:** {stats.get('tool_results', 0)}",
        f"- **Tool cache hits:** {stats.get('tool_cache_hits', 0)}",
        f"- **LLM calls:** {stats.get('llm_calls', 0)}",
        f"- **LLM replies:** {stats.get('llm_replies', 0)}",
        f"- **LLM retries:** {stats.get('llm_retries', 0)}",
        f"- **LLM errors:** {stats.get('llm_errors', 0)}",
        f"- **Tool errors:** {stats.get('tool_errors', 0)}",
        f"- **Tool timeouts:** {stats.get('tool_timeouts', 0)}",
        f"- **Run time:** {_format_duration_ms(stats.get('duration_ms'))}",
        f"- **Model:** `{stats.get('used_model') or 'n/a'}`",
        f"- **LLM models:** {_format_counts(stats.get('llm_model_counts') or {})}",
        f"- **Tools:** {_format_counts(stats.get('tool_counts') or {})}",
        "",
    ]
    return "\n".join(lines)


def _run_once(app: Flask, run_id: str) -> None:
    with app.app_context():
        run = AgentRun.query.filter_by(id=run_id).first()
        if not run:
            return
        if run.status != "queued":
            return
        try:
            session = ChatSession.query.filter_by(id=run.chat_session_id, user_id=run.user_id).first()
            workspace = Workspace.query.filter_by(id=run.workspace_id, user_id=run.user_id).first()
            if not session or not workspace:
                run.status = "error"
                run.error_text = "Session or workspace missing for run."
                run.finished_at = datetime.utcnow()
                _append_event(run, "error", {"error": run.error_text})
                db.session.commit()
                return

            run.status = "running"
            run.started_at = datetime.utcnow()
            _append_event(run, "running", {"started_at": run.started_at.isoformat()})
            db.session.commit()

            set_runtime_context(run.user_id, run.workspace_id, run.chat_session_id, run.id)

            # Log the user's query text from the last user message
            last_user_msg = (
                Message.query
                .filter_by(user_id=run.user_id, chat_session_id=run.chat_session_id, role="user")
                .order_by(Message.created_at.desc())
                .first()
            )
            actlog.log(EVT_USER_MSG, {
                "query": (last_user_msg.content[:500] if last_user_msg else ""),
                "workspace_id": run.workspace_id,
                "session_id": run.chat_session_id,
            })
            actlog.log(EVT_RUN_START, {
                "run_id": run.id,
                "workspace_id": run.workspace_id,
                "session_id": run.chat_session_id,
                "max_steps": get_user_react_max_steps(run.user_id),
            })

            db_messages = (
                Message.query
                .filter_by(user_id=run.user_id, chat_session_id=run.chat_session_id)
                .order_by(Message.created_at.asc())
                .all()
            )
            history = to_langchain_messages([
                {"role": row.role, "content": row.content}
                for row in db_messages
            ])

            # Inject project memory as a system message prefix if present.
            if session.project_id:
                project = Project.query.filter_by(id=session.project_id, user_id=run.user_id).first()
                if project and project.memory_text:
                    memory_msg = SystemMessage(content=f"[Project Memory]\n{project.memory_text}")
                    history = [memory_msg] + list(history)

            available_tools = workspace.tool_ids or []
            if not available_tools:
                from .tools import TOOL_MAP

                available_tools = list(TOOL_MAP.keys())

            max_steps = get_user_react_max_steps(run.user_id)
            graph = get_react_graph()
            config = {"configurable": {"thread_id": f"{run.user_id}:{run.chat_session_id}:{run.id}"}}
            input_state = {
                "messages": history,
                "available_tools": available_tools,
                "step_count": 0,
                "max_steps": max_steps,
                "final_answer": None,
                "used_model": "",
                "user_id": run.user_id,
                "workspace_id": run.workspace_id,
                "session_id": run.chat_session_id,
                "run_id": run.id,
            }

            for mode, event in graph.stream(input_state, config, stream_mode=["updates", "messages"]):
                if mode != "updates":
                    continue
                for node_name, node_update in event.items():
                    payload = {
                        "node": node_name,
                        "used_model": node_update.get("used_model", ""),
                    }
                    if node_name == "tool_executor":
                        messages = node_update.get("messages") or []
                        if messages:
                            first_message = messages[0]
                            payload["tool_name"] = getattr(first_message, "name", "") or node_update.get("tool_name") or ""
                            payload["tool_result"] = str(first_message.content)
                    if node_name == "agent_node":
                        messages = node_update.get("messages") or []
                        if messages:
                            payload["agent_message"] = str(messages[0].content or "")
                    _append_event(run, "step", payload)
                db.session.commit()

            final_state = graph.get_state(config)
            raw_answer = resolve_final_answer(final_state.values or {}) or "(no answer)"

            run.finished_at = datetime.utcnow()
            usage_stats = _build_usage_stats(run, final_state)
            graph_messages = (final_state.values or {}).get("messages") or []
            final_answer = _format_usage_stats(usage_stats) + append_deterministic_sources(raw_answer, graph_messages)

            run.status = "done"
            run.final_answer = final_answer
            _append_event(run, "done", {"finished_at": run.finished_at.isoformat()})

            duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000) if run.started_at else None
            actlog.log(EVT_RUN_DONE, {
                "run_id": run.id,
                "answer_len": len(final_answer),
                "used_model": (final_state.values or {}).get("used_model", ""),
                "usage_stats": usage_stats,
            }, duration_ms=duration_ms)

            assistant_message = Message(
                user_id=run.user_id,
                chat_session_id=run.chat_session_id,
                role="assistant",
                content=final_answer,
                metadata_json={"run_id": run.id, "mode": "react", "usage_stats": usage_stats},
            )
            db.session.add(assistant_message)

            session.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            run = AgentRun.query.filter_by(id=run_id).first()
            if not run:
                return
            run.status = "error"
            run.error_text = str(exc)
            run.finished_at = datetime.utcnow()
            _append_event(run, "error", {"error": str(exc)})
            actlog.log(EVT_RUN_ERROR, {"run_id": run_id, "error": str(exc)[:500]})
            db.session.commit()
