"""Gunicorn config for Alfred.

Deployment invariant (P1 #1): workers MUST be 1. Alfred is single-process by
design (in-memory keepalive timers in alfred/keepalive.py, process-local
`_active_timers`). Multiple workers would split timers across processes and
break the Runtime Manager keepalive contract. Reject any multi-worker override.
"""

import os
import sys


def _validate_workers():
    # Honor an explicit GUNICORN_WORKERS only if it is exactly 1; otherwise force 1.
    explicit = os.environ.get("GUNICORN_WORKERS")
    if explicit is not None and explicit.strip() != "1":
        sys.stderr.write(
            "WARN: Alfred requires workers=1 (single-process keepalive). "
            "Ignoring GUNICORN_WORKERS=%s and forcing workers=1.\n" % explicit
        )
    return 1


workers = _validate_workers()
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:5950")
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "120"))
graceful_timeout = 30
keepalive = 5
worker_class = "sync"
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("GUNICORN_LOGLEVEL", "info")
