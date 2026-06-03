from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path


def get_sync_log_path() -> Path:
    base_dir = os.environ.get("LOCALAPPDATA")
    if not base_dir:
        base_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    path = Path(base_dir) / "ABasu_apps" / "NoteStack" / "sync.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    if not path.exists():
        try:
            path.touch()
        except OSError:
            pass
    return path


def get_sync_logger() -> logging.Logger:
    logger = logging.getLogger("notestack.sync")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = logging.handlers.RotatingFileHandler(
        get_sync_log_path(),
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    logger.addHandler(handler)
    return logger