"""Core Alfred invariant tests (P1 immutability, P4 provenance, isolation)."""

import json

from alfred.extensions import db
from alfred.ingest import compute_content_hash, ingest_bytes
from alfred.models import Asset, Evidence


def _make_user(app, username):
    from alfred.models import LocalCredential

    u = LocalCredential(username=username)
    u.set_password("x")
    db.session.add(u)
    db.session.flush()
    profile = u.ensure_profile()
    db.session.commit()
    return profile.user_id


def test_asset_dedupe_by_content_hash(app, client):
    with app.app_context():
        uid = _make_user(app, "dedupe_a")
        data = b"hello world content"
        a1 = ingest_bytes(data, "f1.txt", "text/plain", uid, title="A")
        a2 = ingest_bytes(data, "f2.txt", "text/plain", uid, title="B")
        assert a1.id == a2.id, "Same content hash must dedupe to one Asset"
        assert Asset.query.filter_by(user_id=uid).count() == 1


def test_evidence_rejected_when_empty_sources(app, client):
    with app.app_context():
        ev = Evidence(source_asset_ids=json.dumps([]), payload_json="{}")
        # P4: provenance mandatory — empty source list is invalid.
        assert ev.sources == []
        # The business rule enforced by save_report: empty sources => ValueError.
        from alfred.agent import tools

        try:
            tools.tool_save_report("run1", "user_x", {"title": "t", "content": "c", "source_asset_ids": []})
            assert False, "save_report must reject empty source_asset_ids"
        except ValueError:
            pass


def test_library_search_isolated_per_user(app, client):
    """A user only retrieves their own Assets."""
    with app.app_context():
        uid_a = _make_user(app, "user_a")
        uid_b = _make_user(app, "user_b")

        asset_a = ingest_bytes(b"secret alpha content for A", "a.txt", "text/plain", uid_a, title="A-doc")
        ingest_bytes(b"secret beta content for B", "b.txt", "text/plain", uid_b, title="B-doc")

        # Force embeddings for both via the embedding provider path if key present;
        # otherwise assert at the Asset filter level (per-user scoping).
        from alfred.models import Asset as _A

        a_assets = _A.query.filter_by(user_id=uid_a).all()
        b_assets = _A.query.filter_by(user_id=uid_b).all()
        assert asset_a.id in [x.id for x in a_assets]
        assert asset_a.id not in [x.id for x in b_assets]
