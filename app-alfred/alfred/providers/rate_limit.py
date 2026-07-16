"""Simple in-process rate limiter for external provider calls."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    def __init__(self, max_calls: int, window_seconds: float):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self._calls = []
        self._lock = threading.Lock()

    def acquire(self):
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            self._calls = [t for t in self._calls if t > cutoff]
            if len(self._calls) >= self.max_calls:
                wait = self._calls[0] + self.window_seconds - now
                if wait > 0:
                    time.sleep(min(wait, self.window_seconds))
            self._calls.append(time.monotonic())
