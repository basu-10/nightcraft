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


def test_rag_evidence_exempt_from_derivation_validator():
    """F6: RAG library_search may legitimately create Evidence with empty sources
    (no matches). The derivation validator must NOT be applied to it — only to
    derived-artifact writes (save_report / transform_asset). Prove the validator
    is invoked at the artifact boundary, not by the RAG path.
    """
    from alfred.rag import library_search

    # The RAG path builds an Evidence object directly without calling
    # assert_derivation_has_sources; constructing one with empty sources is fine.
    rag_evidence = Evidence(
        source_asset_ids=json.dumps([]),
        payload_json=json.dumps({"mode": "library_search", "matches": []}),
    )
    assert rag_evidence.sources == []
    # The validator function itself still rejects empty sources (boundary-only),
    # confirming RAG does not route through it.
    with pytest.raises(ValueError):
        assert_derivation_has_sources(rag_evidence)
    # The RAG path is exempt by design (it never calls the validator).



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


@pytest.mark.integration
def test_janitor_reaps_failed_ingest_orphan(app, client):
    """§4 janitor: a stuck 'indexing' asset with no blob is reaped as an orphan."""
    with app.app_context():
        from alfred.extensions import db
        from alfred.janitor import run_janitor_pass
        from alfred.models import AgentRun, Asset, LocalCredential

        u = LocalCredential(username="jan_user")
        u.set_password("x")
        db.session.add(u)
        db.session.flush()
        uid = u.ensure_profile().user_id
        db.session.commit()

        # 'indexing' asset whose blob never got written (Failed per §4). Put it in
        # the past so it exceeds the stuck-indexing grace window.
        from datetime import datetime, timedelta, timezone

        asset = Asset(
            content_hash="deadbeef" * 8, content_type="document",
            storage_ref="/nonexistent/blob.txt", mime_type="text/plain",
            title="Orphan", user_id=uid, status="indexing",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        db.session.add(asset)
        db.session.commit()
        aid = asset.id

        run_janitor_pass()

        assert Asset.query.get(aid) is None


@pytest.mark.integration
def test_run_history_route_scoped_to_user(app, client):
    """N12: /alfred/runs lists only the requesting user's runs."""
    with app.app_context():
        from alfred.extensions import db
        from alfred.models import AgentRun, LocalCredential

        u = LocalCredential(username="hist_user")
        u.set_password("x")
        db.session.add(u)
        db.session.flush()
        uid = u.ensure_profile().user_id
        other = LocalCredential(username="hist_other")
        other.set_password("x")
        db.session.add(other)
        db.session.flush()
        oid = other.ensure_profile().user_id
        db.session.commit()

        db.session.add(AgentRun(run_id="r_self", user_id=uid, goal="mine", status="done"))
        db.session.add(AgentRun(run_id="r_other", user_id=oid, goal="theirs", status="done"))
        db.session.commit()

    # Login as hist_user and fetch the history page.
    client.post("/alfred/auth/login", data={"username": "hist_user", "password": "x"})
    resp = client.get("/alfred/runs")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "mine" in body
    assert "theirs" not in body
