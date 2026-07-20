"""Tests for IMPLEMENTATION_PIPELINE items.

Pure-logic tests (policy clock, capability classification, evidence validator,
input pinning hash, asset-isolation helper) run without a database. DB-backed
tests reuse the shared `app` fixture and are skipped when DATABASE_URL is unset.
"""

import json

import pytest

from alfred.agent.executor import _RuntimePolicy, _PolicyClock
from alfred.agent.planner import _classify_capability, plan_goal_capability
from alfred.models import Evidence, assert_derivation_has_sources
from alfred.api import _pin_input_hash


# --- P1 #2 Runtime policies: clock + guard logic (no DB) ---


def test_policy_clock_injects_fake_now():
    state = {"t": 1000.0}

    def fake():
        return state["t"]

    clock = _PolicyClock(now_fn=fake)
    assert clock.now() == 1000.0
    state["t"] = 1005.0
    assert clock.now() == 1005.0


def test_policy_max_runtime_exceeded():
    state = {"t": 0.0}

    def fake():
        return state["t"]

    p = _RuntimePolicy(max_runtime=10)
    p._clock = _PolicyClock(now_fn=fake)
    p.start()
    assert p.exceeded()[0] is False
    state["t"] = 11.0
    exceeded, reason = p.exceeded()
    assert exceeded is True
    assert "max runtime" in reason


def test_policy_idle_timeout_exceeded():
    from datetime import datetime, timedelta, timezone

    start = datetime.now(timezone.utc) - timedelta(seconds=60)
    p = _RuntimePolicy(idle_timeout=30)
    p.start(started_at=start)
    exceeded, reason = p.exceeded()
    assert exceeded is True
    assert "idle timeout" in reason


def test_policy_token_budget_exceeded():
    p = _RuntimePolicy(token_budget=100)
    p.start()
    p.touch(tokens=50)
    assert p.exceeded()[0] is False
    p.touch(tokens=60)
    exceeded, reason = p.exceeded()
    assert exceeded is True
    assert "token budget" in reason


def test_policy_cost_budget_exceeded():
    p = _RuntimePolicy(cost_budget=1.0)
    p.start()
    p.touch(cost=0.5)
    assert p.exceeded()[0] is False
    p.touch(cost=0.8)
    exceeded, reason = p.exceeded()
    assert exceeded is True
    assert "cost budget" in reason


def test_policy_unbounded_when_none():
    p = _RuntimePolicy()
    p.start()
    assert p.exceeded()[0] is False


# --- P2 #4 Evidence boundary validator (no DB) ---


def test_assert_derivation_rejects_none():
    with pytest.raises(ValueError):
        assert_derivation_has_sources(None)


def test_assert_derivation_rejects_empty_sources():
    ev = Evidence(source_asset_ids=json.dumps([]), payload_json="{}")
    with pytest.raises(ValueError):
        assert_derivation_has_sources(ev)


def test_assert_derivation_accepts_sources():
    ev = Evidence(source_asset_ids=json.dumps(["1"]), payload_json="{}")
    assert assert_derivation_has_sources(ev) is True


# --- P2 #13 Capability classification (no DB) ---


def test_classify_capability_transform():
    plan = {"phases": [{"phase": "transform", "allowed_tools": ["transform_asset"]}]}
    assert _classify_capability(plan) == "transform"


def test_classify_capability_retrieve():
    plan = {"phases": [{"phase": "retrieve", "allowed_tools": ["library_search"]}]}
    assert _classify_capability(plan) == "retrieve"


def test_classify_capability_research_default():
    plan = {"phases": [{"phase": "research", "allowed_tools": ["web_search"]}]}
    assert _classify_capability(plan) == "research"


def test_plan_goal_capability_shape():
    cap = plan_goal_capability("summarize Q3 earnings", "does_not_exist_user")
    assert set(cap) == {"capability", "capability_version", "manifest_hash"}
    assert cap["capability_version"]
    assert len(cap["manifest_hash"]) == 64


# --- P2 #5 Asset isolation helper (no DB) ---


def test_require_owned_asset_aborts_on_missing():
    from flask import Flask

    from alfred.guards import require_owned_asset

    scratch = Flask("scratch")

    class _User:
        user_id = "user_a"

    with scratch.test_request_context():
        with pytest.raises(Exception):
            require_owned_asset(999999, _User())


# --- DB-backed tests (skipped without DATABASE_URL) ---


@pytest.mark.integration
def test_run_records_capability_and_input_hash(app, client):
    with app.app_context():
        from alfred.extensions import db
        from alfred.ingest import ingest_bytes
        from alfred.models import AgentRun, LocalCredential

        u = LocalCredential(username="cap_user")
        u.set_password("x")
        db.session.add(u)
        db.session.flush()
        uid = u.ensure_profile().user_id
        db.session.commit()

        a = ingest_bytes(b"source content", "s.txt", "text/plain", uid, title="S")
        pinned = _pin_input_hash([a.id])
        run = AgentRun(
            run_id="run_cap", user_id=uid, goal="g", status="queued",
            capability="research", capability_version="1.0.0",
            manifest_hash="x" * 64, run_input_hash=pinned,
        )
        db.session.add(run)
        db.session.commit()
        got = AgentRun.query.filter_by(run_id="run_cap").first()
        assert got.capability == "research"
        assert got.run_input_hash == pinned
        assert _pin_input_hash([a.id]) != _pin_input_hash([])
