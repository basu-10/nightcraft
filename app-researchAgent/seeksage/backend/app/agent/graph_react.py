from __future__ import annotations

import time

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import Send
from langgraph.graph import END, START, StateGraph

from .llm_factory import build_agent_llms, build_summary_llms
from .models import ReactState
from .prompts import REACT_SYSTEM_PROMPT
from .tool_cache import get_tool_cache
from .tools import TOOL_MAP
from ..core import activity_log as actlog
from ..core.activity_log import (
    EVT_LLM_CALL, EVT_LLM_REPLY, EVT_LLM_RETRY, EVT_LLM_ERROR,
    EVT_TOOL_CALL, EVT_TOOL_RESULT, EVT_TOOL_CACHE_HIT, EVT_TOOL_ERROR,
)


_graph = None
_checkpointer = None


def _get_checkpointer() -> MemorySaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = MemorySaver()
    return _checkpointer


def get_react_graph():
    global _graph
    if _graph is None:
        checkpointer = _get_checkpointer()
        builder = StateGraph(ReactState)
        builder.add_node("agent_node", react_agent_node)
        builder.add_node("tool_executor", react_tool_executor_node)
        builder.add_edge(START, "agent_node")
        builder.add_conditional_edges("agent_node", route_react, ["tool_executor", END])
        builder.add_edge("tool_executor", "agent_node")
        _graph = builder.compile(checkpointer=checkpointer)
    return _graph


def react_agent_node(state: ReactState) -> dict:
    messages = state.get("messages") or []
    available = state.get("available_tools") or []
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 5)
    user_id = state.get("user_id")
    workspace_id = state.get("workspace_id")
    session_id = state.get("session_id", "")
    run_id = state.get("run_id", "")

    tools = [TOOL_MAP[name] for name in available if name in TOOL_MAP]
    is_last_step = (step_count + 1) >= max_steps

    if is_last_step:
        synthesized, synth_model = _synthesize_terminal_answer(
            messages,
            user_id=user_id,
            workspace_id=workspace_id,
            step_count=step_count,
            session_id=session_id,
            run_id=run_id,
        )
        if synthesized:
            return {
                "messages": [AIMessage(content=synthesized)],
                "step_count": step_count + 1,
                "used_model": synth_model or "",
                "final_answer": synthesized,
            }

    lc_messages = [SystemMessage(content=REACT_SYSTEM_PROMPT)] + list(messages)

    last_exc = None
    for llm, model_name in build_agent_llms(user_id, workspace_id):
        t0 = time.monotonic()
        actlog.log(
            EVT_LLM_CALL,
            {"model": model_name, "step": step_count, "is_last": is_last_step},
            user_id=user_id, session_id=session_id, run_id=run_id,
        )
        try:
            bound = llm if (is_last_step or not tools) else llm.bind_tools(tools)
            response: AIMessage = bound.invoke(lc_messages)
            duration_ms = int((time.monotonic() - t0) * 1000)
            has_tool_calls = bool(getattr(response, "tool_calls", None))

            content = response.content
            if isinstance(content, list):
                content = " ".join(
                    piece.get("text", "") if isinstance(piece, dict) else str(piece)
                    for piece in content
                )
            content_len = len(content or "")

            actlog.log(
                EVT_LLM_REPLY,
                {
                    "model": model_name,
                    "step": step_count,
                    "content_len": content_len,
                    "tool_calls": len(getattr(response, "tool_calls", None) or []),
                },
                user_id=user_id, session_id=session_id, run_id=run_id,
                duration_ms=duration_ms,
            )

            final = (content or "").strip() if not has_tool_calls else None
            return {
                "messages": [response],
                "step_count": step_count + 1,
                "used_model": model_name,
                "final_answer": final,
            }
        except Exception as exc:
            last_exc = exc
            duration_ms = int((time.monotonic() - t0) * 1000)
            actlog.log(
                EVT_LLM_RETRY,
                {"model": model_name, "step": step_count, "error": str(exc)[:300]},
                user_id=user_id, session_id=session_id, run_id=run_id,
                duration_ms=duration_ms,
            )

    actlog.log(
        EVT_LLM_ERROR,
        {"step": step_count, "error": str(last_exc)[:300]},
        user_id=user_id, session_id=session_id, run_id=run_id,
    )
    raise RuntimeError(f"All LLMs failed in react_agent_node. Last error: {last_exc}")


def route_react(state: ReactState):
    step_count = state.get("step_count", 0)
    max_steps = state.get("max_steps", 5)
    if step_count >= max_steps:
        return END

    messages = state.get("messages") or []
    last_ai = None
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            last_ai = message
            break

    if not last_ai or not getattr(last_ai, "tool_calls", None):
        return END

    sends = []
    for tool_call in last_ai.tool_calls:
        sends.append(
            Send(
                "tool_executor",
                {
                    "tool_call_id": tool_call["id"],
                    "tool_name": tool_call["name"],
                    "tool_args": dict(tool_call.get("args") or {}),
                    "available_tools": state.get("available_tools") or [],
                    # Propagate identifiers so each parallel thread can set its TLS
                    "user_id":    state.get("user_id", ""),
                    "session_id": state.get("session_id", ""),
                    "run_id":     state.get("run_id", ""),
                },
            )
        )
    return sends


def react_tool_executor_node(state: dict) -> dict:
    tool_call_id = state["tool_call_id"]
    tool_name = state["tool_name"]
    tool_args = dict(state.get("tool_args") or {})
    user_id   = state.get("user_id", "")
    session_id = state.get("session_id", "")
    run_id    = state.get("run_id", "")

    # Propagate context into this thread's TLS so tool-level logs are tagged
    actlog.set_log_context(user_id, session_id, run_id)

    cache = get_tool_cache()
    cached = cache.get(tool_name, tool_args)
    if cached is not None:
        actlog.log(
            EVT_TOOL_CACHE_HIT,
            {"tool": tool_name},
            user_id=user_id, session_id=session_id, run_id=run_id,
        )
        return {"messages": [ToolMessage(content=cached, tool_call_id=tool_call_id, name=tool_name)]}

    actlog.log(
        EVT_TOOL_CALL,
        {"tool": tool_name, "args": {k: str(v)[:120] for k, v in tool_args.items()}},
        user_id=user_id, session_id=session_id, run_id=run_id,
    )
    t0 = time.monotonic()
    try:
        tool_fn = TOOL_MAP.get(tool_name)
        if tool_fn is None:
            raise ValueError(f"Tool '{tool_name}' not found")

        # Remove hallucinated keys not declared by tool schema.
        known_keys = set(tool_fn.args.keys())
        clean_args = {key: value for key, value in tool_args.items() if key in known_keys}

        result = tool_fn.invoke(clean_args)
        content = str(result)
        duration_ms = int((time.monotonic() - t0) * 1000)
        cache.put(tool_name, tool_args, content)
        actlog.log(
            EVT_TOOL_RESULT,
            {"tool": tool_name, "result_len": len(content)},
            user_id=user_id, session_id=session_id, run_id=run_id,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        content = f"[TOOL ERROR] {tool_name}: {exc}"
        actlog.log(
            EVT_TOOL_ERROR,
            {"tool": tool_name, "error": str(exc)[:300]},
            user_id=user_id, session_id=session_id, run_id=run_id,
            duration_ms=duration_ms,
        )

    return {"messages": [ToolMessage(content=content, tool_call_id=tool_call_id, name=tool_name)]}


def resolve_final_answer(final_state_values: dict) -> str:
    final_answer = final_state_values.get("final_answer")
    if final_answer:
        return str(final_answer).strip()

    synthesized, _ = _synthesize_terminal_answer(
        final_state_values.get("messages") or [],
        user_id=final_state_values.get("user_id", ""),
        workspace_id=final_state_values.get("workspace_id", ""),
        step_count=final_state_values.get("step_count", 0),
        session_id=final_state_values.get("session_id", ""),
        run_id=final_state_values.get("run_id", ""),
    )
    if synthesized:
        return synthesized

    messages = final_state_values.get("messages") or []
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not getattr(message, "tool_calls", None):
            content = message.content
            if isinstance(content, list):
                content = " ".join(
                    piece.get("text", "") if isinstance(piece, dict) else str(piece)
                    for piece in content
                )
            if content:
                return str(content).strip()

    return ""


def to_langchain_messages(db_messages: list[dict]):
    result = []
    for message in db_messages:
        role = message.get("role")
        content = message.get("content") or ""
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        elif role == "tool":
            result.append(ToolMessage(content=content, tool_call_id="legacy_tool"))
    return result


def _normalize_content(content) -> str:
    if isinstance(content, list):
        return " ".join(
            piece.get("text", "") if isinstance(piece, dict) else str(piece)
            for piece in content
        ).strip()
    return str(content or "").strip()


def _synthesize_terminal_answer(
    messages: list,
    *,
    user_id: str,
    workspace_id: str,
    step_count: int,
    session_id: str,
    run_id: str,
) -> tuple[str, str]:
    if not messages or not user_id or not workspace_id:
        return "", ""

    last_human_idx = max(
        (i for i, message in enumerate(messages) if isinstance(message, HumanMessage)),
        default=-1,
    )
    current_turn = messages[last_human_idx:] if last_human_idx >= 0 else messages
    tool_results = [m for m in current_turn if isinstance(m, ToolMessage)]

    if tool_results:
        results_text = "\n\n".join(
            f"[{idx + 1}] Tool result:\n{_normalize_content(m.content)}"
            for idx, m in enumerate(tool_results)
        )
    else:
        results_text = ""

    tool_names = set()
    for message in reversed(current_turn):
        if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
            for tool_call in message.tool_calls:
                name = tool_call.get("name")
                if name:
                    tool_names.add(name)
            break

    only_artifacts = bool(tool_names) and tool_names.issubset({"create_slides", "save_text"})
    history_for_synth = [
        m for m in messages
        if isinstance(m, (HumanMessage, AIMessage)) and not (
            isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
        )
    ]

    if only_artifacts and results_text:
        synth_user_content = (
            "The following file-creation tool(s) just ran. "
            "Write a single short sentence (max 2 sentences) confirming what was saved and where. "
            "Do not summarize the underlying research content.\n\n"
            f"Tool results:\n{results_text}"
        )
        llm_messages = [
            SystemMessage(content=REACT_SYSTEM_PROMPT),
            HumanMessage(content=synth_user_content),
        ]
    elif results_text:
        synth_user_content = (
            "Based on the following tool results, provide the best final answer for the user's latest request. "
            "If any tool failed, mention that clearly and continue with available information.\n\n"
            f"Tool results:\n{results_text}"
        )
        llm_messages = [SystemMessage(content=REACT_SYSTEM_PROMPT)] + history_for_synth + [
            HumanMessage(content=synth_user_content)
        ]
    else:
        llm_messages = [
            SystemMessage(content=REACT_SYSTEM_PROMPT),
            HumanMessage(content="Provide the best final answer for the latest user request."),
        ] + history_for_synth

    last_exc = None
    for llm, model_name in build_summary_llms(user_id, workspace_id):
        t0 = time.monotonic()
        actlog.log(
            EVT_LLM_CALL,
            {"model": model_name, "step": step_count, "purpose": "terminal_synthesis"},
            user_id=user_id, session_id=session_id, run_id=run_id,
        )
        try:
            response: AIMessage = llm.invoke(llm_messages)
            answer = _normalize_content(getattr(response, "content", ""))
            if answer:
                actlog.log(
                    EVT_LLM_REPLY,
                    {
                        "model": model_name,
                        "step": step_count,
                        "purpose": "terminal_synthesis",
                        "content_len": len(answer),
                    },
                    user_id=user_id,
                    session_id=session_id,
                    run_id=run_id,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
                return answer, model_name
        except Exception as exc:
            last_exc = exc
            actlog.log(
                EVT_LLM_RETRY,
                {
                    "model": model_name,
                    "step": step_count,
                    "purpose": "terminal_synthesis",
                    "error": str(exc)[:300],
                },
                user_id=user_id,
                session_id=session_id,
                run_id=run_id,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    if last_exc is not None:
        actlog.log(
            EVT_LLM_ERROR,
            {
                "step": step_count,
                "purpose": "terminal_synthesis",
                "error": str(last_exc)[:300],
            },
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
        )
    return "", ""
