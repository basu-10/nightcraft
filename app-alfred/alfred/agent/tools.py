"""Agent tool implementations used by the Workflow executor."""

from __future__ import annotations

import json
import os
import uuid

from ..extensions import db
from ..ingest import ingest_bytes
from ..models import (
    ASSET_TYPE_REPORT,
    Asset,
    AssetRelation,
    Evidence,
    assert_derivation_has_sources,
)
from ..providers import LLMProvider, web_search as web_provider
from ..rag import library_search as rag_search
from .events import emit_event


def _ensure_dirs():
    from flask import current_app

    base = current_app.config.get("UPLOADS_DIR", "uploads")
    if not os.path.isabs(base):
        base = os.path.join(current_app.instance_path, base)
    reports_dir = os.path.join(base, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    return reports_dir


def tool_library_search(run_id, user_id, args):
    query = (args or {}).get("query", "")
    evidence = rag_search(query, user_id)
    return {
        "sources": evidence.sources,
        "matches": evidence.payload.get("matches", []),
        "note": "Citations reference the user's own library assets.",
    }


def tool_web_search(run_id, user_id, args):
    query = (args or {}).get("query", "")
    results = web_provider.web_search(query, max_results=5)
    return {"results": results}


def tool_wiki_search(run_id, user_id, args):
    query = (args or {}).get("query", "")
    results = web_provider.web_search(f"{query} site:wikipedia.org", max_results=3)
    return {"results": results}


def tool_visit_url(run_id, user_id, args):
    url = (args or {}).get("url", "")
    text = web_provider.visit_url(url, max_chars=8000)
    if not text:
        return {"url": url, "text": "", "imported_asset_id": None, "error": "Could not fetch URL."}
    asset = ingest_bytes(
        text.encode("utf-8"),
        filename=url.split("/")[-1] or "web_import",
        mime_type="text/plain",
        user_id=user_id,
        title=url,
        source_url=url,
    )
    return {"url": url, "text": text, "imported_asset_id": asset.id}


def tool_save_report(run_id, user_id, args):
    """Create a Report Asset + derived_from relations + provenance Evidence (P4)."""
    title = (args or {}).get("title", "Alfred Report")
    content = (args or {}).get("content", "")
    source_asset_ids = (args or {}).get("source_asset_ids", []) or []

    if not source_asset_ids:
        # Provenance is mandatory (P4): reject Evidence/derivation with empty sources.
        emit_event(run_id, user_id, "error", {"message": "save_report requires non-empty source_asset_ids (provenance)."})
        raise ValueError("save_report requires non-empty source_asset_ids for provenance (P4).")

    reports_dir = _ensure_dirs()
    stored_name = f"{uuid.uuid4().hex}.md"
    storage_ref = os.path.join(reports_dir, stored_name)
    with open(storage_ref, "w", encoding="utf-8") as fh:
        fh.write(content)

    asset = Asset(
        content_hash=_hash_text(content),
        content_type=ASSET_TYPE_REPORT,
        storage_ref=storage_ref,
        mime_type="text/markdown",
        title=title,
        user_id=user_id,
        status="ready",
        metadata_json=json.dumps({
            "kind": "report",
            "word_count": len(content.split()),
            # P3 #9: this is a generated markdown version derived from sources;
            # the originals remain unchanged.
            "is_generated_version": True,
            "is_original": False,
            "original_preserved": True,
        }),
    )
    db.session.add(asset)
    db.session.flush()

    for src_id in source_asset_ids:
        try:
            src_id_int = int(src_id)
        except (TypeError, ValueError):
            continue
        db.session.add(
            AssetRelation(from_id=asset.id, to_id=src_id_int, relation_type="derived_from")
        )

    evidence = Evidence(
        source_asset_ids=json.dumps([str(s) for s in source_asset_ids]),
        payload_json=json.dumps({"report_asset_id": asset.id, "title": title}),
        run_id=run_id,
    )
    db.session.add(evidence)
    db.session.flush()
    # Boundary validator (P2 #4): never persist a derived artifact without provenance.
    assert_derivation_has_sources(evidence)
    asset.lineage_json = json.dumps({"generated_by_run": run_id, "evidence_id": evidence.id})
    db.session.commit()

    emit_event(run_id, user_id, "artifact", {"asset_id": asset.id, "title": title, "kind": "report"})
    return {"asset_id": asset.id, "title": title, "storage_ref": storage_ref}


def tool_transform_asset(run_id, user_id, args):
    """Edit/rewrite an attached Asset into a NEW version_of Report Asset (P1 immutable)."""
    source_asset_id = (args or {}).get("asset_id")
    instruction = (args or {}).get("instruction", "")
    title = (args or {}).get("title")

    if not source_asset_id:
        emit_event(run_id, user_id, "error", {"message": "transform_asset requires asset_id."})
        raise ValueError("transform_asset requires asset_id.")

    source = Asset.query.filter_by(id=int(source_asset_id), user_id=user_id).first()
    if not source:
        raise ValueError("Source asset not found or not owned by user.")

    source_text = _load_asset_text(source)
    new_title = title or f"{source.title} (edited)"

    prompt = [
        {
            "role": "system",
            "content": "You are an editing assistant. Apply the user's instruction to the provided "
            "document and return the FULL rewritten document in markdown. Do not modify the original; "
            "produce a new version. Respond with the rewritten document only.",
        },
        {
            "role": "user",
            "content": f"INSTRUCTION:\n{instruction}\n\n--- SOURCE DOCUMENT ---\n{source_text}",
        },
    ]
    try:
        rewritten = LLMProvider.chat(prompt, max_tokens=4000)
    except Exception as exc:
        emit_event(run_id, user_id, "error", {"message": f"transform failed: {exc}"})
        raise

    reports_dir = _ensure_dirs()
    stored_name = f"{uuid.uuid4().hex}.md"
    storage_ref = os.path.join(reports_dir, stored_name)
    with open(storage_ref, "w", encoding="utf-8") as fh:
        fh.write(rewritten)

    asset = Asset(
        content_hash=_hash_text(rewritten),
        content_type=ASSET_TYPE_REPORT,
        storage_ref=storage_ref,
        mime_type="text/markdown",
        title=new_title,
        user_id=user_id,
        status="ready",
        metadata_json=json.dumps({
            "kind": "report",
            "transform_of": source.id,
            "is_generated_version": True,
            "is_original": False,
            "original_preserved": True,
        }),
    )
    db.session.add(asset)
    db.session.flush()

    db.session.add(AssetRelation(from_id=asset.id, to_id=source.id, relation_type="version_of"))
    db.session.add(AssetRelation(from_id=asset.id, to_id=source.id, relation_type="derived_from"))

    evidence = Evidence(
        source_asset_ids=json.dumps([str(source.id)]),
        payload_json=json.dumps({"report_asset_id": asset.id, "title": new_title, "instruction": instruction}),
        run_id=run_id,
    )
    db.session.add(evidence)
    db.session.flush()
    assert_derivation_has_sources(evidence)
    asset.lineage_json = json.dumps({"generated_by_run": run_id, "evidence_id": evidence.id})
    db.session.commit()

    emit_event(run_id, user_id, "artifact", {"asset_id": asset.id, "title": new_title, "kind": "report"})
    return {"asset_id": asset.id, "title": new_title, "storage_ref": storage_ref}


def _load_asset_text(asset: Asset) -> str:
    from ..models import AssetChunk

    chunks = AssetChunk.query.filter_by(asset_id=asset.id).order_by(AssetChunk.chunk_index.asc()).all()
    if chunks:
        return "\n\n".join(c.text for c in chunks)
    # Fallback: read file.
    try:
        with open(asset.storage_ref, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return ""


def _hash_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


TOOLS = {
    "library_search": tool_library_search,
    "web_search": tool_web_search,
    "wiki_search": tool_wiki_search,
    "visit_url": tool_visit_url,
    "save_report": tool_save_report,
    "transform_asset": tool_transform_asset,
}
