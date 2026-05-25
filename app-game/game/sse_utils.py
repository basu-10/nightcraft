import json
import time

from flask import current_app


def _sse(data: dict) -> str:
    payload = json.dumps(data, default=str)
    return f"data: {payload}\n\n"


def sse_event(event_type: str, **kwargs) -> str:
    return _sse({"event": event_type, **kwargs})


def format_sse(data: str) -> str:
    return f"data: {data}\n\n"


def heartbeat() -> str:
    return sse_event("heartbeat")


def stream_with_heartbeat(gen, interval: int = 15):
    last_beat = time.time()
    for chunk in gen:
        now = time.time()
        if now - last_beat >= interval:
            yield heartbeat()
            last_beat = now
        yield chunk
