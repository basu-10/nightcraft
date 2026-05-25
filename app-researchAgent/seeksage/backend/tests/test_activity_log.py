"""PostgreSQL-backed tests for the activity logging system."""

from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.activity_log import ActivityLogger, set_log_context


TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()

if not TEST_DATABASE_URL:
    pytest.skip("TEST_DATABASE_URL is required for PostgreSQL-backed tests.", allow_module_level=True)


def _make_logger() -> ActivityLogger:
    logger = ActivityLogger(TEST_DATABASE_URL)
    logger.start()
    return logger


def _count(logger: ActivityLogger, run_id: str) -> int:
    with logger.engine.connect() as con:
        return con.execute(
            text("SELECT COUNT(*) FROM activity_log WHERE run_id = :run_id"),
            {"run_id": run_id},
        ).scalar_one()


def _wait_for_count(logger: ActivityLogger, run_id: str, expected: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _count(logger, run_id) >= expected:
            return True
        time.sleep(0.05)
    return False


@pytest.mark.unit
def test_single_record_written():
    logger = _make_logger()
    run_id = f"test-single-{uuid4()}"
    logger.log("test_event", {"key": "value"}, user_id="u1", run_id=run_id)

    assert _wait_for_count(logger, run_id, 1)


@pytest.mark.unit
def test_thread_local_context():
    logger = _make_logger()
    run_id = f"test-context-{uuid4()}"

    set_log_context("ctx-user", "ctx-session", run_id)
    logger.log("ctx_test")

    assert _wait_for_count(logger, run_id, 1)
    with logger.engine.connect() as con:
        row = con.execute(
            text(
                "SELECT user_id, session_id, run_id "
                "FROM activity_log WHERE run_id = :run_id ORDER BY id DESC LIMIT 1"
            ),
            {"run_id": run_id},
        ).mappings().one()

    assert row["user_id"] == "ctx-user"
    assert row["session_id"] == "ctx-session"
    assert row["run_id"] == run_id


@pytest.mark.unit
def test_parallel_threads_all_written():
    logger = _make_logger()
    run_id = f"test-parallel-{uuid4()}"
    n_threads = 6
    n_per_thread = 15
    total = n_threads * n_per_thread
    errors: list[str] = []

    def worker(thread_id: int) -> None:
        try:
            set_log_context(f"user-{thread_id}", f"session-{thread_id}", run_id)
            for j in range(n_per_thread):
                logger.log("parallel_test", {"thread": thread_id, "j": j})
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert _wait_for_count(logger, run_id, total, timeout=10.0)


@pytest.mark.unit
def test_cleanup_removes_old_rows():
    logger = _make_logger()
    run_id = f"test-cleanup-{uuid4()}"

    with logger.engine.begin() as con:
        con.execute(
            text(
                "INSERT INTO activity_log "
                "(ts, event_type, user_id, session_id, run_id, data_json) "
                "VALUES ('2000-01-01T00:00:00+00:00', 'old_event', 'u1', '', :run_id, '{}')"
            ),
            {"run_id": run_id},
        )

    logger._cleanup_sync()

    with logger.engine.connect() as con:
        remaining = con.execute(
            text(
                "SELECT COUNT(*) FROM activity_log "
                "WHERE run_id = :run_id AND event_type = 'old_event'"
            ),
            {"run_id": run_id},
        ).scalar_one()

    assert remaining == 0
