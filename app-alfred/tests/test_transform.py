"""Tests for the differentiating transform/edit operation and save_report provenance (P4)."""

import json

from alfred.agent import tools
from alfred.extensions import db
from alfred.ingest import ingest_bytes
from alfred.models import Asset, AssetRelation, Evidence, AssetEmbedding, AssetChunk


def _seed_user(app):
    from alfred.models import LocalCredential

    u = LocalCredential(username="xform_user")
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    uid = u.ensure_profile().user_id
    db.session.commit()
    return uid


def _stub_llm(monkeypatch, reply):
    def _fake_chat(messages, model=None, temperature=0.2, max_tokens=2000, response_format=None):
        return reply

    monkeypatch.setattr(tools.LLMProvider, "chat", staticmethod(_fake_chat))


def test_transform_asset_emits_new_version_of_report(app, client, monkeypatch, tmp_path):
    with app.app_context():
        uid = _seed_user(app)
        source = ingest_bytes(
            b"Introduction: the market is growing.\nBody: details here.",
            "src.txt", "text/plain", uid, title="Source Doc",
        )
        monkeypatch.setattr("alfred.agent.tools._load_asset_text", lambda a: "Introduction: the market is growing.\nBody: details here.")
        _stub_llm(monkeypatch, "# Rewritten\nThe market is expanding rapidly.\n- point one\n- point two")

        result = tools.tool_transform_asset(
            "run_x", uid,
            {"asset_id": str(source.id), "instruction": "reformat as bullets", "title": "Edited Doc"},
        )
        assert result["asset_id"] != source.id
        new_asset = Asset.query.get(result["asset_id"])
        assert new_asset.content_type == "report"
        # P1 immutability: original unchanged.
        assert Asset.query.get(source.id).metadata_json  # still present

        # version_of + derived_from relations exist (P1 provenance).
        rels = AssetRelation.query.filter_by(from_id=new_asset.id).all()
        types = {r.relation_type for r in rels}
        assert "version_of" in types
        assert "derived_from" in types
        # P4 provenance: Evidence cites the source.
        ev = Evidence.query.filter_by(run_id="run_x").first()
        assert str(source.id) in ev.sources


def test_save_report_requires_provenance(app, client, monkeypatch):
    """save_report must create derived_from relation from source_asset_ids (P4)."""
    with app.app_context():
        uid = _seed_user(app)
        source = ingest_bytes(b"some source text", "s.txt", "text/plain", uid, title="Src")
        monkeypatch.setattr("alfred.agent.tools._load_asset_text", lambda a: "x")
        _stub_llm(monkeypatch, "report body")

        result = tools.tool_save_report(
            "run_r", uid,
            {"title": "Report", "content": "# Report\nbody", "source_asset_ids": [str(source.id)]},
        )
        report = Asset.query.get(result["asset_id"])
        rel = AssetRelation.query.filter_by(from_id=report.id, to_id=source.id, relation_type="derived_from").first()
        assert rel is not None
        ev = Evidence.query.filter_by(run_id="run_r").first()
        assert str(source.id) in ev.sources
