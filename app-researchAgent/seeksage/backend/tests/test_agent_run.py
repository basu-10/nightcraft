"""
test_agent_run.py — Full end-to-end agent run tests using the real OpenRouter API.

These tests:
 1. Create a full DB context (user, workspace, session, profile)
 2. Enqueue a real agent run with a live LLM
 3. Call _run_once() directly (bypassing the background worker thread)
 4. Assert the run completes with a sensible answer
 5. Log everything to the activity log with test-run identifiers

Test cases are driven from fixtures/agent_cases.yaml.
Skip automatically if OPENROUTER_API_KEY is not set.

Isolation
---------
Each test creates its own AgentRun row and chat session so runs cannot
interfere with each other. All DB writes go to the session-scoped
the configured PostgreSQL test database (from conftest.py).
"""

from __future__ import annotations

import os
import time
import uuid

import pytest
import yaml


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_agent_cases() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "fixtures", "agent_cases.yaml")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return (data or {}).get("cases", [])


_SKIP_LIVE = pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set — skipping live agent tests",
)


def _actlog_run_test(case_id: str, status: str, answer: str, duration_ms: int, error: str = ""):
    from app.core import activity_log as actlog
    actlog.log(
        "test_agent_run",
        {
            "case_id":      case_id,
            "status":       status,
            "answer_preview": answer[:400] if answer else "",
            "answer_len":   len(answer),
            "error":        error[:400] if error else "",
        },
        user_id="test-harness",
        run_id=f"test:{case_id}",
        duration_ms=duration_ms,
    )


def _create_run(app, db, test_user, test_ws, case: dict) -> tuple[str, str]:
    """Create a ChatSession + Message + AgentRun for one test case. Returns (session_id, run_id)."""
    from app.models import AgentRun, ChatSession, Message

    sess = ChatSession(
        user_id=test_user,
        workspace_id=test_ws,
        title=f"test:{case['id']}",
        thread_id=str(uuid.uuid4()),
    )
    db.session.add(sess)
    db.session.flush()

    msg = Message(
        user_id=test_user,
        chat_session_id=sess.id,
        role="user",
        content=case["prompt"],
    )
    db.session.add(msg)
    db.session.flush()

    run = AgentRun(
        user_id=test_user,
        workspace_id=test_ws,
        chat_session_id=sess.id,
        query_text=case["prompt"],
        status="queued",
    )
    db.session.add(run)
    db.session.commit()
    return sess.id, run.id


# ── Tests ──────────────────────────────────────────────────────────────────────

@_SKIP_LIVE
@pytest.mark.live
@pytest.mark.slow
class TestAgentRunLive:
    """Full agent runs against live OpenRouter. Each case from agent_cases.yaml."""

    def _execute_run(self, app, db, test_user, test_ws, or_profile, case: dict) -> dict:
        """
        Creates DB rows, executes _run_once() synchronously, returns summary dict.
        """
        timeout_s = case.get("timeout_s", 120)

        with app.app_context():
            # Override workspace tools if case specifies them
            from app.models import Workspace
            ws = Workspace.query.get(test_ws)
            original_tools = list(ws.tool_ids)
            if case.get("tools"):
                ws.tool_ids = case["tools"]
                db.session.commit()

            sess_id, run_id = _create_run(app, db, test_user, test_ws, case)

        t0 = time.monotonic()

        # Run the agent synchronously (no worker thread needed)
        from app.agent.runner import _run_once
        try:
            _run_once(app, run_id)
        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            _actlog_run_test(case["id"], "exception", "", elapsed, str(exc))
            pytest.fail(f"_run_once raised: {exc}")

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        assert elapsed_ms / 1000 <= timeout_s, (
            f"Run exceeded timeout ({elapsed_ms/1000:.1f}s > {timeout_s}s)"
        )

        with app.app_context():
            from app.models import AgentRun, Message
            run = AgentRun.query.get(run_id)
            assert run is not None
            answer = run.final_answer or ""
            status = run.status
            error  = run.error_text or ""

            # Restore original tools
            from app.models import Workspace
            ws = Workspace.query.get(test_ws)
            ws.tool_ids = original_tools
            db.session.commit()

        _actlog_run_test(case["id"], status, answer, elapsed_ms, error)
        return {"status": status, "answer": answer, "error": error, "elapsed_ms": elapsed_ms}

    # ── Parametrised from YAML ─────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "case",
        _load_agent_cases(),
        ids=[c["id"] for c in _load_agent_cases()],
    )
    def test_agent_case(self, app, _db_obj, test_user, test_ws, or_profile, case):
        result = self._execute_run(app, _db_obj, test_user, test_ws, or_profile, case)

        assert result["status"] == "done", (
            f"Run did not complete. status={result['status']} error={result['error']}"
        )

        answer_lower = result["answer"].lower()

        for kw in (case.get("expect") or []):
            if isinstance(kw, list):
                continue  # empty expect list — no keyword assertions
            assert kw.lower() in answer_lower, (
                f"case={case['id']}: expected '{kw}' in answer.\n"
                f"Answer preview: {result['answer'][:500]}"
            )

        for forbidden in (case.get("forbid") or []):
            assert forbidden.lower() not in answer_lower, (
                f"case={case['id']}: forbidden string '{forbidden}' found in answer."
            )


# ── Smoke test (always runs — just checks LLM factory can build a chain) ───────

@pytest.mark.integration
class TestLLMFactory:
    def test_build_agent_llms_returns_list(self, app, test_user, test_ws):
        with app.app_context():
            from app.agent.llm_factory import build_agent_llms
            chain = build_agent_llms(test_user, test_ws)
            # Even with no profile set, should return at least one entry
            assert isinstance(chain, list)
            assert len(chain) >= 1
            llm, name = chain[0]
            assert callable(getattr(llm, "invoke", None))
            assert isinstance(name, str) and len(name) > 0

    @_SKIP_LIVE
    @pytest.mark.live
    def test_llm_factory_live_call(self, app, test_user, test_ws, or_profile):
        """Verify the LLM chain makes a real call and returns a string."""
        with app.app_context():
            from langchain_core.messages import HumanMessage
            from app.agent.llm_factory import build_agent_llms, invoke_with_fallbacks
            chain = build_agent_llms(test_user, test_ws)
            t0 = time.monotonic()
            response, model_name = invoke_with_fallbacks(
                chain, [HumanMessage(content="Respond with exactly: pong")]
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            content = getattr(response, "content", str(response))
            from app.core import activity_log as actlog
            actlog.log(
                "test_llm_ping",
                {"model": model_name, "response": content[:200]},
                user_id="test-harness",
                duration_ms=elapsed_ms,
            )
            assert "pong" in content.lower(), f"Unexpected LLM response: {content}"

    @_SKIP_LIVE
    @pytest.mark.live
    def test_build_summary_llms(self, app, test_user, test_ws, or_profile):
        with app.app_context():
            from app.agent.llm_factory import build_summary_llms
            chain = build_summary_llms(test_user, test_ws)
            assert isinstance(chain, list) and len(chain) >= 1

    @_SKIP_LIVE
    @pytest.mark.live
    def test_build_code_llms(self, app, test_user, test_ws, or_profile):
        with app.app_context():
            from app.agent.llm_factory import build_code_llms
            chain = build_code_llms(test_user, test_ws)
            assert isinstance(chain, list) and len(chain) >= 1
