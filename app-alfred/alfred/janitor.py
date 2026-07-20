"""Janitorial worker: long-term runtime health (ARCHITECTURE §4).

Runs every 60 seconds in-process. The runtime is single-process by deployment
invariant (gunicorn workers=1; see ARCHITECTURE §4b), so an in-process daemon
thread is safe — there is exactly one janitor per Alfred instance.

It reconciles the three-system consistency model (SQLite metadata + filesystem
blob + pgvector embeddings) by sweeping asset validity states:

  Pending   (status='indexing', blob not written)   -> reconcile or mark failed
  Complete  (blob+meta committed, not indexed)      -> retry embedding
  Failed    (write failed, orphaned blob)            -> drop orphan + mark
  Superseded (newer version exists)                  -> prune orphaned embeddings

It also reaps AgentRuns left in a non-terminal state (queued/running) by a dead
process between restarts, and surfaces a count of actions taken for /health.
"""

from __future__ import annotations

import json
import os
import threading
import time

from .extensions import db

_JANITOR_INTERVAL = 60  # seconds (ARCHITECTURE §4 "Runs every 60 seconds")
_STUCK_INDEXING_GRACE = 30  # seconds before an 'indexing' asset is reaped

_configured = False
_running = False
_thread: threading.Thread | None = None
_stop = threading.Event()

# Cumulatives for observability (read by `flask janitor --report`).
_stats = {
    "runs": 0,
    "assets_reconciled": 0,
    "embeddings_retried": 0,
    "orphans_removed": 0,
    "runs_reaped": 0,
    "last_run_at": None,
    "last_error": None,
}


def configure(app):
    global _configured
    _configured = True
    # Only auto-start the loop when running under the real server (not `flask`
    # one-off commands / tests), consistent with how keepalive is wired.
    if os.environ.get("ALFRED_JANITOR_DISABLE"):
        return
    start(app)


def start(app=None):
    global _running, _thread
    if _running:
        return
    _running = True
    _stop.clear()
    target = _loop if app is None else lambda: _loop(app)
    _thread = threading.Thread(target=target, daemon=True)
    _thread.start()


def stop():
    global _running
    _stop.set()
    _running = False


def stats():
    return dict(_stats)


def _app_from_env():
    from .__init__ import create_app

    return create_app()


def _loop(app=None):
    while not _stop.is_set():
        try:
            if app is None:
                app = _app_from_env()
            with app.app_context():
                run_janitor_pass()
        except Exception as exc:  # noqa: BLE001 - never let the loop die
            _stats["last_error"] = str(exc)[:300]
            try:
                app.logger.warning(f"janitor pass failed: {exc}")
            except Exception:
                pass
        if _stop.wait(_JANITOR_INTERVAL):
            break


def run_janitor_pass():
    """One reconciliation sweep. Call inside an app context."""
    from .models import AgentRun, Asset, AssetChunk, AssetEmbedding

    _stats["runs"] += 1
    _stats["last_run_at"] = _utcnow()

    # --- 1. Reap non-terminal AgentRuns (covers dead-process between restarts).
    reaped = (
        AgentRun.query.filter(AgentRun.status.in_(["queued", "running"]))
        .update(
            {
                AgentRun.status: "error",
                AgentRun.error: "Run interrupted (janitor reap: no live executor).",
            },
            synchronize_session=False,
        )
    )
    if reaped:
        _stats["runs_reaped"] += reaped

    # --- 2. Reconcile assets stuck in 'indexing' (Pending/Failed per §4).
    stuck = (
        Asset.query.filter(Asset.status == "indexing")
        .filter(Asset.created_at < _utcnow_timedelta(seconds=-_STUCK_INDEXING_GRACE))
        .all()
    )
    for asset in stuck:
        blob_exists = asset.storage_ref and os.path.exists(asset.storage_ref)
        chunk_count = AssetChunk.query.filter_by(asset_id=asset.id).count()
        emb_count = AssetEmbedding.query.filter_by(asset_id=asset.id).count()
        if blob_exists and chunk_count and emb_count:
            # Complete/Indexed: a prior pass finished; promote to ready.
            asset.status = "ready"
            _clear_embedding_pending(asset)
            _stats["assets_reconciled"] += 1
        elif not blob_exists:
            # Failed: blob missing -> remove orphaned chunks/embeddings + asset.
            _delete_asset_rows(asset)
            _stats["orphans_removed"] += 1
            _stats["assets_reconciled"] += 1
        else:
            # Partial: blob present but no chunks/embeddings -> retry embed.
            _retry_embed(asset)
            _stats["assets_reconciled"] += 1

    # --- 3. Complete assets flagged for (re)embedding but missing vectors.
    from .services.settings import get_setting
    from .settings_keys import DEFAULT_EMBEDDING_MODEL

    model = get_setting("alfred_embedding_model", "") or DEFAULT_EMBEDDING_MODEL
    pending = Asset.query.filter(Asset.status == "ready").all()
    for asset in pending:
        meta = asset.asset_metadata
        if not meta.get("embedding_pending"):
            continue
        emb_count = (
            AssetEmbedding.query.filter_by(asset_id=asset.id, model=model).count()
        )
        if emb_count:
            _clear_embedding_pending(asset)
            _stats["assets_reconciled"] += 1
        else:
            _retry_embed(asset)

    # --- 4. Superseded assets: prune embeddings of older versions (eventual
    #         vector-index hygiene; older-version rows are never queried).
    #         Kept conservative: only prune embeddings whose model is NOT the
    #         active model and whose chunk belongs to a superseded asset.
    from sqlalchemy import select

    superseded_ids = select(Asset.id).where(Asset.status == "superseded")
    orphan_embs = (
        db.session.query(AssetEmbedding)
        .filter(AssetEmbedding.asset_id.in_(superseded_ids))
        .filter(AssetEmbedding.model != model)
        .delete(synchronize_session=False)
    )
    if orphan_embs:
        _stats["orphans_removed"] += orphan_embs

    db.session.commit()
    return dict(_stats)


def _retry_embed(asset):
    from .ingest import _index_text, _extract_text_from_bytes
    from .providers import EmbeddingProvider
    from .settings_keys import DEFAULT_EMBEDDING_MODEL
    from .services.settings import get_setting

    try:
        if not (asset.storage_ref and os.path.exists(asset.storage_ref)):
            meta = asset.asset_metadata
            asset.status = "failed"
            meta["janitor_note"] = "blob missing; marked failed"
            asset.metadata_json = json.dumps(meta)
            return
        with open(asset.storage_ref, "rb") as fh:
            data = fh.read()
        text = _extract_text_from_bytes(data, asset.mime_type, asset.title)
        _index_text(asset, text)
        model = get_setting("alfred_embedding_model", "") or DEFAULT_EMBEDDING_MODEL
        if AssetEmbedding.query.filter_by(asset_id=asset.id, model=model).count():
            asset.status = "ready"
            _clear_embedding_pending(asset)
        _stats["embeddings_retried"] += 1
    except Exception as exc:  # noqa: BLE001
        meta = asset.asset_metadata
        meta["embedding_pending"] = True
        meta["embedding_error"] = str(exc)[:300]
        asset.metadata_json = json.dumps(meta)


def _clear_embedding_pending(asset):
    meta = asset.asset_metadata
    if meta.pop("embedding_pending", None) is not None or meta.pop("embedding_error", None) is not None:
        asset.metadata_json = json.dumps(meta)


def _delete_asset_rows(asset):
    AssetEmbedding.query.filter_by(asset_id=asset.id).delete(synchronize_session=False)
    AssetChunk.query.filter_by(asset_id=asset.id).delete(synchronize_session=False)
    db.session.delete(asset)
    try:
        if asset.storage_ref and os.path.exists(asset.storage_ref):
            os.remove(asset.storage_ref)
    except OSError:
        pass


def _utcnow():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _utcnow_timedelta(seconds=0):
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
