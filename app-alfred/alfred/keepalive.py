"""Backend run-keepalive: hold Alfred up while an AgentRun is running.

While a run is in `running` state, this timer calls POST http://127.0.0.1:5700/touch/alfred
directly (bypassing nginx) every ~20s so the Runtime Manager never stops Alfred
mid-task. Stops when the run reaches done/error. (Plan §11.)
"""

from __future__ import annotations

import threading
import time

import requests

_MANAGER_TOUCH_URL = None
_KEEPALIVE_INTERVAL = 20

_active_timers: dict[str, threading.Event] = {}
_lock = threading.Lock()


def configure(app):
    global _MANAGER_TOUCH_URL
    _MANAGER_TOUCH_URL = app.config.get("RUNTIME_MANAGER_URL", "http://127.0.0.1:5700").rstrip("/") + "/touch/alfred"


def start_run_keepalive(run_id: str, app=None):
    stop_event = threading.Event()
    with _lock:
        _active_timers[run_id] = stop_event

    def _loop():
        while not stop_event.is_set():
            _touch_manager()
            if stop_event.wait(_KEEPALIVE_INTERVAL):
                break

    t = threading.Thread(target=_loop, daemon=True)
    t.start()


def stop_run_keepalive(run_id: str):
    with _lock:
        ev = _active_timers.pop(run_id, None)
    if ev is not None:
        ev.set()


def _touch_manager():
    if not _MANAGER_TOUCH_URL:
        return
    try:
        requests.post(_MANAGER_TOUCH_URL, timeout=2)
    except Exception:
        pass
