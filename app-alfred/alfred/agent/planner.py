"""Hybrid Planner: emits a high-level phase plan shown to the user."""

from __future__ import annotations

import json

from ..models import Asset
from ..providers import LLMProvider

PLANNER_SYSTEM = """You are Alfred's Planner. Given a user goal and a summary of the
user's personal Asset library, decide the high-level phases needed to fulfill the
goal. For each phase, specify which tools are ALLOWED during that phase.

Tool vocabulary:
- library_search: search the user's own ingested Asset library (RAG). Use when the
  library likely already contains the answer.
- web_search: general web search. Use when up-to-date or external info is needed.
- wiki_search: encyclopedic / reference lookup.
- visit_url: fetch and read a specific URL (also imports it as a library Asset).
- save_report: write the final synthesized Report Asset.
- transform_asset: edit/rewrite an attached Asset into a new Report Asset. Use when
  the goal is to change/format an attached file.

Routing guidance (RAG vs non-RAG): if the library summary shows relevant assets, you
SHOULD include a 'retrieve' phase whose allowed_tools contain only 'library_search'.
You may then add a 'research' phase with web tools for gaps. If the library is empty
or unrelated, emit a 'research' phase with web tools instead. If the goal references
an attached asset and asks to change/reformat it, emit a 'transform' phase with
'transform_asset'.

Respond ONLY with a JSON object:
{
  "phases": [
    {"phase": "retrieve", "allowed_tools": ["library_search"], "intent": "..."},
    {"phase": "research", "allowed_tools": ["web_search","visit_url"], "intent": "..."},
    {"phase": "synthesize", "allowed_tools": [], "intent": "..."},
    {"phase": "generate_report", "allowed_tools": ["save_report"], "intent": "..."}
  ]
}
"""


def library_summary(user_id: str) -> str:
    assets = Asset.query.filter_by(user_id=user_id, status="ready").order_by(Asset.created_at.desc()).limit(25).all()
    if not assets:
        return "Library is EMPTY (no ingested assets)."
    lines = [f"- {a.title} ({a.content_type})" for a in assets]
    return f"Library has {len(assets)} asset(s):\n" + "\n".join(lines)


def plan_goal(goal: str, user_id: str) -> dict:
    summary = library_summary(user_id)
    try:
        plan = LLMProvider.chat_json(
            [
                {"role": "system", "content": PLANNER_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"USER GOAL:\n{goal}\n\n"
                        f"USER LIBRARY SUMMARY:\n{summary}\n\n"
                        "Emit the phase plan as JSON."
                    ),
                },
            ]
        )
    except Exception:
        plan = None

    if not plan or not isinstance(plan.get("phases"), list) or not plan["phases"]:
        plan = _fallback_plan(goal, summary)

    return plan


def _fallback_plan(goal: str, summary: str) -> dict:
    phases = [
        {"phase": "research", "allowed_tools": ["web_search", "visit_url", "wiki_search"], "intent": "Research the goal on the web."},
        {"phase": "synthesize", "allowed_tools": [], "intent": "Synthesize findings."},
        {"phase": "generate_report", "allowed_tools": ["save_report"], "intent": "Produce the final Report Asset."},
    ]
    if "EMPTY" not in summary:
        phases.insert(
            0,
            {"phase": "retrieve", "allowed_tools": ["library_search"], "intent": "Check the user's library first."},
        )
    return {"phases": phases}
