"""Workflow executor: runs the Planner's phases sequentially.

Within each phase it runs a ReAct-style loop where the LLM may call only that
phase's allowed_tools. This realizes the spec's Planner (fixes WHAT may happen)
vs Workflow (dynamically chooses within bounds) separation (P6).

A LangGraph graph is available as an alternative wiring, but the core loop is
self-contained so Alfred does not depend on LangGraph at runtime. The plan's
"sequential phases + per-phase ReAct budget" contract is honored either way.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from ..extensions import db
from ..models import AgentRun
from ..providers import LLMProvider, web_search as web_provider
from ..settings_keys import resolve_agent_model, resolve_react_max_steps
from .events import (
    EVT_ARTIFACT,
    EVT_ERROR,
    EVT_LLM_MESSAGE,
    EVT_PLAN,
    EVT_STATUS,
    EVT_TOOL_CALL,
    EVT_TOOL_RESULT,
    emit_event,
)
from .tools import TOOLS


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "library_search",
            "description": "Search the user's own ingested Asset library (RAG). Returns cited chunks.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "General web search. Returns result titles/urls/snippets.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "wiki_search",
            "description": "Encyclopedic / reference lookup (Wikipedia).",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Lookup query."}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "visit_url",
            "description": "Fetch and read a specific URL; also imports it as a library Asset.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Fully-qualified URL."}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_report",
            "description": "Write the final synthesized Report Asset. Requires source_asset_ids (provenance).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string", "description": "Full markdown report."},
                    "source_asset_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Asset ids this report is derived from (citations).",
                    },
                },
                "required": ["title", "content", "source_asset_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transform_asset",
            "description": "Edit/rewrite an attached Asset into a NEW version_of Report Asset (original unchanged).",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string", "description": "Attached/session Asset id."},
                    "instruction": {"type": "string", "description": "Edit instruction."},
                    "title": {"type": "string"},
                },
                "required": ["asset_id", "instruction"],
            },
        },
    },
]


def _system_prompt(goal, phase_intent, allowed_tools, collected_sources):
    tool_list = ", ".join(allowed_tools) if allowed_tools else "(no tools — synthesize)"
    citations = "\n".join(f"- asset {s}" for s in collected_sources) or "(none yet)"
    return (
        f"You are Alfred's Workflow executor for the '{phase_intent}' phase of this goal:\n{goal}\n\n"
        f"During this phase you may ONLY call these tools: {tool_list}.\n"
        f"Assets already cited so far:\n{citations}\n\n"
        "When you have enough information, respond with a concise synthesis OR call save_report/"
        "transform_asset to finalize. Do not call tools outside the allowed set. After save_report or "
        "transform_asset, reply with a short final summary and stop."
    )


class _PolicyClock:
    """Wall-clock source for runtime policies. Injectable for tests (fake clock)."""

    def __init__(self, now_fn=None):
        self._now_fn = now_fn or (lambda: time.monotonic())

    def now(self):
        return self._now_fn()


class _RuntimePolicy:
    """Bounded runtime / idle / budget guard for a single AgentRun (P1 #2).

    A run is aborted with status ``fatal`` when any bound is exceeded:
      - wall-clock runtime > ``max_runtime_seconds`` (None => unbounded)
      - gap since last activity > ``idle_timeout_seconds`` (None => unbounded)
      - cumulative tokens > ``token_budget`` (None => unbounded)
      - cumulative cost > ``cost_budget_usd`` (None => unbounded)
    """

    def __init__(self, max_runtime=None, idle_timeout=None, token_budget=None, cost_budget=None):
        self.max_runtime = max_runtime
        self.idle_timeout = idle_timeout
        self.token_budget = token_budget
        self.cost_budget = cost_budget
        self.last_activity = None
        self.tokens_used = 0
        self.cost_usd = 0.0
        self._clock = _PolicyClock()

    def start(self, started_at=None):
        now = _utcnow() if started_at is None else started_at
        self.last_activity = now
        self._start_wall = self._clock.now()

    def touch(self, tokens=0, cost=0.0):
        self.last_activity = _utcnow()
        self._clock.now()  # advance monotonic reference only via clock
        self.tokens_used += tokens
        self.cost_usd += cost

    def _exceeded(self):
        """Return (exceeded: bool, reason: str)."""
        wall = self._clock.now() - self._start_wall
        if self.max_runtime is not None and wall > self.max_runtime:
            return True, f"max runtime {self.max_runtime}s exceeded ({wall:.0f}s)"
        if self.idle_timeout is not None:
            idle = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
            if idle > self.idle_timeout:
                return True, f"idle timeout {self.idle_timeout}s exceeded ({idle:.0f}s)"
        if self.token_budget is not None and self.tokens_used > self.token_budget:
            return True, f"token budget {self.token_budget} exceeded ({self.tokens_used})"
        if self.cost_budget is not None and self.cost_usd > self.cost_budget:
            return True, f"cost budget ${self.cost_budget} exceeded (${self.cost_usd:.2f})"
        return False, ""

    def exceeded(self):
        return self._exceeded()

    def exceeded_reason(self):
        return self._exceeded()[1]


def run_workflow(run_id: str, user_id: str, goal: str, plan: dict, attached_asset_ids=None):
    run = AgentRun.query.filter_by(run_id=run_id).first()
    if run is None:
        return

    emit_event(run_id, user_id, EVT_PLAN, {"plan": plan})
    emit_event(run_id, user_id, EVT_STATUS, {"status": "running"})

    attached_asset_ids = list(attached_asset_ids or [])
    collected_sources = list(attached_asset_ids)
    model = resolve_agent_model()
    max_steps = resolve_react_max_steps()

    policy = _RuntimePolicy(
        max_runtime=run.max_runtime_seconds,
        idle_timeout=run.idle_timeout_seconds,
        token_budget=run.token_budget,
        cost_budget=run.cost_budget_usd,
    )
    policy.start(started_at=run.started_at or _utcnow())
    run.started_at = run.started_at or _utcnow()
    run.last_activity_at = run.last_activity_at or _utcnow()

    try:
        for phase in plan.get("phases", []):
            phase_name = phase.get("phase", "phase")
            allowed = phase.get("allowed_tools", []) or []
            intent = phase.get("intent", phase_name)
            emit_event(run_id, user_id, EVT_STATUS, {"status": "running", "phase": phase_name})

            messages = [
                {"role": "system", "content": _system_prompt(goal, intent, allowed, collected_sources)},
                {"role": "user", "content": goal},
            ]

            steps = 0
            final_summary = None
            while steps < max_steps:
                steps += 1

                exceeded, reason = policy.exceeded()
                if exceeded:
                    emit_event(run_id, user_id, EVT_ERROR, {"message": f"Run terminated: {reason}"})
                    raise RuntimeError(f"Runtime policy violation: {reason}")

                try:
                    resp = LLMProvider_openai_chat(model, messages, allowed)
                except Exception as exc:
                    emit_event(run_id, user_id, EVT_ERROR, {"message": f"LLM error in {phase_name}: {exc}"})
                    raise

                msg = resp.choices[0].message
                if getattr(msg, "content", None):
                    emit_event(run_id, user_id, EVT_LLM_MESSAGE, {"phase": phase_name, "content": msg.content})
                    messages.append({"role": "assistant", "content": msg.content})
                else:
                    messages.append({"role": "assistant", "content": "", "tool_calls": msg.tool_calls})

                tool_calls = getattr(msg, "tool_calls", None)
                if not tool_calls:
                    final_summary = msg.content
                    break

                for tc in tool_calls:
                    fn_name = tc.function.name
                    try:
                        fn_args = json.loads(tc.function.arguments or "{}")
                    except (ValueError, TypeError):
                        fn_args = {}
                    if allowed and fn_name not in allowed:
                        emit_event(
                            run_id, user_id, EVT_TOOL_CALL, {"name": fn_name, "args": fn_args, "denied": True}
                        )
                        result = {"error": f"Tool {fn_name} not allowed in phase {phase_name}."}
                    elif fn_name in TOOLS:
                        emit_event(run_id, user_id, EVT_TOOL_CALL, {"name": fn_name, "args": fn_args})
                        try:
                            result = TOOLS[fn_name](run_id, user_id, fn_args)
                        except Exception as exc:
                            emit_event(run_id, user_id, EVT_ERROR, {"message": f"Tool {fn_name} failed: {exc}"})
                            result = {"error": str(exc)}
                    else:
                        result = {"error": f"Unknown tool {fn_name}."}

                    emit_event(run_id, user_id, EVT_TOOL_RESULT, {"name": fn_name, "result": _truncate(result)})

                    # Refresh activity + accounting for the runtime guard.
                    policy.touch(tokens=0, cost=0.0)
                    run.last_activity_at = _utcnow()
                    db.session.commit()

                    # Collect provenance from any cited sources.
                    for key in ("sources", "asset_id", "imported_asset_id"):
                        val = result.get(key) if isinstance(result, dict) else None
                        if key == "sources" and isinstance(val, list):
                            collected_sources.extend(str(s) for s in val)
                        elif key in ("asset_id", "imported_asset_id") and val:
                            collected_sources.append(str(val))

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": fn_name,
                            "content": json.dumps(_truncate(result), default=str),
                        }
                    )

                # If a finalizing tool was called, allow one more summary turn then stop.
                if any(tc.function.name in ("save_report", "transform_asset") for tc in tool_calls):
                    try:
                        summary_resp = LLMProvider_openai_chat(model, messages, [])
                        if summary_resp.choices[0].message.content:
                            emit_event(run_id, user_id, EVT_LLM_MESSAGE, {"phase": phase_name, "content": summary_resp.choices[0].message.content})
                            final_summary = summary_resp.choices[0].message.content
                    except Exception:
                        pass
                    break

            if final_summary:
                emit_event(run_id, user_id, EVT_LLM_MESSAGE, {"phase": phase_name, "final": True, "content": final_summary})

        emit_event(run_id, user_id, EVT_STATUS, {"status": "done", "summary": final_summary or "Completed."})
        run.status = "done"
        run.plan_json = json.dumps(plan)
        db.session.commit()
    except Exception as exc:
        emit_event(run_id, user_id, EVT_ERROR, {"message": f"Run failed: {exc}"})
        run.status = "fatal" if "Runtime policy violation" in str(exc) else "error"
        run.error = str(exc)
        db.session.commit()


def LLMProvider_openai_chat(model, messages, allowed_tools):
    from openai import OpenAI

    from ..providers import _api_key, _openai_client

    client = _openai_client()
    kwargs = dict(model=model, messages=messages, temperature=0.2, max_tokens=2500)
    if allowed_tools:
        kwargs["tools"] = [s for s in TOOL_SCHEMAS if s["function"]["name"] in allowed_tools]
        kwargs["tool_choice"] = "auto"
    return client.chat.completions.create(**kwargs)


def _utcnow():
    return datetime.now(timezone.utc)


def _truncate(obj, limit=4000):
    if isinstance(obj, str):
        return obj[:limit]
    if isinstance(obj, dict):
        return {k: _truncate(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate(v, limit) for v in obj[:10]]
    return obj
