"""activity_log.py — synchronous structured activity logger on PostgreSQL.

Each log call writes directly to PostgreSQL under a per-instance lock.
This avoids background workers and keeps behavior predictable under WSGI hosts.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# Event type constants
EVT_USER_MSG = "user_msg"
EVT_LLM_CALL = "llm_call"
EVT_LLM_REPLY = "llm_reply"
EVT_LLM_RETRY = "llm_retry"
EVT_LLM_ERROR = "llm_error"
EVT_TOOL_CALL = "tool_call"
EVT_TOOL_RESULT = "tool_result"
EVT_TOOL_CACHE_HIT = "tool_cache_hit"
EVT_TOOL_ERROR = "tool_error"
EVT_TOOL_RETRY = "tool_retry"
EVT_TOOL_TIMEOUT = "tool_timeout"
EVT_RUN_START = "run_start"
EVT_RUN_DONE = "run_done"
EVT_RUN_ERROR = "run_error"

_RETENTION_DAYS = 30
_CLEANUP_INTERVAL = 86_400

_tls = threading.local()

_logger_instance: ActivityLogger | None = None
_logger_lock = threading.Lock()

_stdlib_log = logging.getLogger(__name__)


class ActivityLogger:
    """Synchronous logger that writes activity rows to PostgreSQL."""

    def __init__(self, database_uri: str) -> None:
        self._engine = create_engine(database_uri, pool_pre_ping=True)
        self._lock = threading.Lock()
        self._started = False
        self._last_cleanup = 0.0

    @property
    def engine(self) -> Engine:
        return self._engine

    def start(self) -> None:
        if self._started:
            return
        self._init_schema()
        self._started = True

    def shutdown(self, timeout: float = 8.0) -> None:
        # Writes are synchronous; nothing to flush.
        pass

    def log(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        if not self._started:
            return

        record = {
            "ts": datetime.now(timezone.utc),
            "event_type": event_type,
            "user_id": user_id or getattr(_tls, "user_id", "") or "",
            "session_id": session_id or getattr(_tls, "session_id", "") or "",
            "run_id": run_id or getattr(_tls, "run_id", "") or "",
            "data_json": json.dumps(data or {}, ensure_ascii=False, default=str),
            "duration_ms": duration_ms,
        }

        with self._lock:
            try:
                with self._engine.begin() as con:
                    con.execute(
                        text(
                            "INSERT INTO activity_log "
                            "(ts, event_type, user_id, session_id, run_id, data_json, duration_ms) "
                            "VALUES (:ts, :event_type, :user_id, :session_id, :run_id, :data_json, :duration_ms)"
                        ),
                        record,
                    )
            except Exception as exc:
                _stdlib_log.warning("actlog: write failed: %s", exc)

            now = time.monotonic()
            if now - self._last_cleanup >= _CLEANUP_INTERVAL:
                self._cleanup_sync()
                self._last_cleanup = now

    def _init_schema(self) -> None:
        with self._engine.begin() as con:
            con.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS activity_log (
                        id BIGSERIAL PRIMARY KEY,
                        ts TIMESTAMPTZ NOT NULL,
                        event_type VARCHAR(64) NOT NULL,
                        user_id VARCHAR(128) NOT NULL DEFAULT '',
                        session_id VARCHAR(128) NOT NULL DEFAULT '',
                        run_id VARCHAR(128) NOT NULL DEFAULT '',
                        data_json TEXT NOT NULL DEFAULT '{}',
                        duration_ms INTEGER
                    )
                    """
                )
            )
            con.execute(text("CREATE INDEX IF NOT EXISTS idx_al_user_ts ON activity_log (user_id, ts)"))
            con.execute(text("CREATE INDEX IF NOT EXISTS idx_al_run ON activity_log (run_id)"))
            con.execute(text("CREATE INDEX IF NOT EXISTS idx_al_session ON activity_log (session_id)"))
            con.execute(text("CREATE INDEX IF NOT EXISTS idx_al_evt_ts ON activity_log (event_type, ts)"))

    def _cleanup_sync(self) -> None:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
            with self._engine.begin() as con:
                result = con.execute(
                    text("DELETE FROM activity_log WHERE ts < :cutoff"),
                    {"cutoff": cutoff},
                )
                deleted = result.rowcount or 0
                if deleted > 0:
                    _stdlib_log.info(
                        "actlog: purged %d records older than %d days",
                        deleted,
                        _RETENTION_DAYS,
                    )
        except Exception as exc:
            _stdlib_log.warning("actlog: cleanup failed: %s", exc)


def set_log_context(user_id: str, session_id: str = "", run_id: str = "") -> None:
    """Set thread-local context for subsequent log() calls in this thread."""
    _tls.user_id = user_id
    _tls.session_id = session_id
    _tls.run_id = run_id


def init_logger(database_uri: str) -> ActivityLogger:
    """Create or return singleton ActivityLogger and ensure schema exists."""
    global _logger_instance
    with _logger_lock:
        if _logger_instance is None:
            _logger_instance = ActivityLogger(database_uri)
            _logger_instance.start()
    return _logger_instance


def get_logger() -> ActivityLogger | None:
    return _logger_instance


def log(event_type: str, data: dict[str, Any] | None = None, **kwargs: Any) -> None:
    if _logger_instance is not None:
        _logger_instance.log(event_type, data, **kwargs)
