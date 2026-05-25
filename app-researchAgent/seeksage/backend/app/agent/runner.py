from __future__ import annotations

from datetime import datetime

from flask import Flask
from langchain_core.messages import SystemMessage

from ..extensions import db
from ..models import AgentRun, ChatSession, Message, Project, RunEvent, Workspace
from ..settings import get_user_react_max_steps
from ..core import activity_log as actlog
from ..core.activity_log import EVT_USER_MSG, EVT_RUN_START, EVT_RUN_DONE, EVT_RUN_ERROR
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
                            payload["tool_result"] = str(messages[0].content)
                    if node_name == "agent_node":
                        messages = node_update.get("messages") or []
                        if messages:
                            payload["agent_message"] = str(messages[0].content or "")
                    _append_event(run, "step", payload)
                db.session.commit()

            final_state = graph.get_state(config)
            raw_answer = resolve_final_answer(final_state.values or {}) or "(no answer)"

            # Inject deterministic source citations.
            graph_messages = (final_state.values or {}).get("messages") or []
            final_answer = append_deterministic_sources(raw_answer, graph_messages)

            run.status = "done"
            run.final_answer = final_answer
            run.finished_at = datetime.utcnow()
            _append_event(run, "done", {"finished_at": run.finished_at.isoformat()})

            duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000) if run.started_at else None
            actlog.log(EVT_RUN_DONE, {
                "run_id": run.id,
                "answer_len": len(final_answer),
                "used_model": (final_state.values or {}).get("used_model", ""),
            }, duration_ms=duration_ms)

            assistant_message = Message(
                user_id=run.user_id,
                chat_session_id=run.chat_session_id,
                role="assistant",
                content=final_answer,
                metadata_json={"run_id": run.id, "mode": "react"},
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
