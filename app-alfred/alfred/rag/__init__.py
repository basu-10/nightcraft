"""RAG retrieval over the per-user Asset library (pgvector cosine top-k)."""

from __future__ import annotations

import json

from sqlalchemy import text

from ..extensions import db
from ..models import Asset, AssetChunk, AssetEmbedding, AssetRelation, Evidence
from ..providers import EmbeddingProvider
from ..services.settings import get_setting
from ..settings_keys import DEFAULT_EMBEDDING_MODEL, resolve_top_k


def _active_embedding_model():
    return get_setting("alfred_embedding_model", "") or DEFAULT_EMBEDDING_MODEL


def library_search(query: str, user_id: str, top_k: int | None = None):
    """Return Evidence with source_asset_ids and matching chunk context.

    Only embeddings whose model equals the active embedding model are used, so
    old-model vectors are excluded until re-indexed.
    """
    top_k = top_k or resolve_top_k()
    model = _active_embedding_model()

    try:
        query_vec = EmbeddingProvider.embed(query, model=model)
    except Exception as exc:
        raise RuntimeError(f"Embedding failed: {exc}") from exc

    vector_json = json.dumps(query_vec)

    sql = text(
        """
        SELECT ae.chunk_id, ae.asset_id, 1 - (ae.embedding::jsonb::text::vector <=> :vec::jsonb::text::vector) AS score
        FROM asset_embedding ae
        JOIN asset a ON a.id = ae.asset_id
        WHERE ae.model = :model AND a.user_id = :user_id
        ORDER BY score DESC
        LIMIT :top_k
        """
    )
    rows = db.session.execute(
        sql, {"vec": vector_json, "model": model, "user_id": user_id, "top_k": top_k}
    ).fetchall()

    matches = []
    source_asset_ids = []
    for chunk_id, asset_id, score in rows:
        chunk = AssetChunk.query.get(chunk_id)
        asset = Asset.query.get(asset_id)
        if not chunk or not asset:
            continue
        source_asset_ids.append(str(asset_id))
        matches.append(
            {
                "asset_id": asset_id,
                "asset_title": asset.title,
                "chunk_index": chunk.chunk_index,
                "score": round(float(score), 4),
                "text": chunk.text,
            }
        )

    evidence = Evidence(
        source_asset_ids=json.dumps(source_asset_ids),
        payload_json=json.dumps({"query": query, "matches": matches, "mode": "library_search"}),
    )
    db.session.add(evidence)
    db.session.commit()

    return evidence


def get_relation_graph(asset_id: int):
    outgoing = AssetRelation.query.filter_by(from_id=asset_id).all()
    incoming = AssetRelation.query.filter_by(to_id=asset_id).all()
    return {
        "outgoing": [{"to_id": r.to_id, "relation_type": r.relation_type} for r in outgoing],
        "incoming": [{"from_id": r.from_id, "relation_type": r.relation_type} for r in incoming],
    }
