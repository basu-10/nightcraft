import os

from flask import current_app


def process_lock_path(app) -> str:
    return app.config.get("AUTOMATED_WORKER_LOCK_FILE") or os.path.join(
        app.instance_path,
        "automated_ingestion.lock",
    )


def acquire_process_lock(lock_path: str):
    """Acquire a non-blocking cross-process lock; returns a file handle when acquired."""
    try:
        import fcntl  # Linux production path
    except ImportError:
        return None

    try:
        lock_file = open(lock_path, "a+", encoding="utf-8")
    except OSError:
        return None

    try:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except OSError:
        try:
            lock_file.close()
        except Exception:
            pass
        return None


def release_process_lock(lock_file) -> None:
    if lock_file is None:
        return

    try:
        import fcntl

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception:
        pass
    finally:
        try:
            lock_file.close()
        except Exception:
            pass


def try_run_with_process_lock(app, func, *args, **kwargs):
    """Run `func` while holding the cross-process ingestion flock.

    Returns the existing `skipped_concurrent` style payload when another
    process already holds the lock, so timer runs and manual triggers never
    overlap.
    """
    lock_path = process_lock_path(app)
    os.makedirs(app.instance_path, exist_ok=True)
    lock_file = acquire_process_lock(lock_path)
    if lock_file is None:
        current_app.logger.info("Automated ingestion skipped: lock held by another process")
        return {
            "run_id": "skipped_concurrent",
            "log_path": None,
            "feed_fetch_limit": 0,
            "new_articles": 0,
            "timestamp_skipped": 0,
            "duplicates_skipped": 0,
            "fetch_failures": 0,
            "processed_channels": 0,
            "processed_feeds": 0,
            "breaking_updates": 0,
            "fatal_error": "Another automation run is already in progress. Try again shortly.",
            "failures": [],
        }
    try:
        return func(*args, **kwargs)
    finally:
        release_process_lock(lock_file)
