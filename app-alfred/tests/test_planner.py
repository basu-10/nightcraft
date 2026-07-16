"""Planner routing tests: RAG path when library has the answer, web otherwise."""

from alfred.agent.planner import plan_goal, _fallback_plan
from alfred.extensions import db
from alfred.models import Asset


def test_planner_emits_retrieve_phase_when_library_populated(app, client):
    with app.app_context():
        from alfred.models import LocalCredential
        from alfred.ingest import ingest_bytes

        u = LocalCredential(username="planner_user")
        u.set_password("x")
        db.session.add(u)
        db.session.flush()
        uid = u.ensure_profile().user_id
        db.session.commit()

        ingest_bytes(b"company Q3 earnings reveal strong growth", "r.txt", "text/plain", uid, title="Report")
        plan = plan_goal("Summarize the Q3 earnings", uid)
        phases = plan.get("phases", [])
        assert any(p["phase"] == "retrieve" for p in phases), "Should propose library_search (RAG) path"


def test_planner_uses_web_when_library_empty(app, client):
    with app.app_context():
        # No assets for this user => no retrieve phase, web research instead.
        plan = plan_goal("What is the weather in Paris today?", "some_other_user")
        phases = plan.get("phases", [])
        assert not any(p["phase"] == "retrieve" for p in phases)
        assert any(p["phase"] in ("research", "generate_report") for p in phases)
