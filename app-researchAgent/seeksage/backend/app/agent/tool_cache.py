"""
Tool result TTL cache — thread-safe, LRU-evicted, no external dependencies.

Caches expensive external tool calls (web search, wiki, URL fetch, etc.)
keyed on (tool_name, canonicalised_args_hash) with per-tool configurable TTLs.

The cache is process-scoped: shared across all workspace worker threads.
Only cacheable tools are stored; create_slides / save_text are never cached.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict

# ── Per-tool TTLs (seconds) ──────────────────────────────────────────────────
_CACHEABLE_TOOLS: dict[str, int] = {
    "web_search":    600,   # 10 min
    "news_search":   300,   #  5 min
    "wiki_search":  3600,   # 60 min
    "arxiv_search": 3600,   # 60 min
    "visit_url":     900,   # 15 min
}

_MAX_ENTRIES = 256


class ToolResultCache:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: OrderedDict[str, tuple[str, float]] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, tool_name: str, args: dict) -> str | None:
        if tool_name not in _CACHEABLE_TOOLS:
            return None
        key = self._make_key(tool_name, args)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            result, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self._misses += 1
                return None
            self._store.move_to_end(key)
            self._hits += 1
            return result

    def put(self, tool_name: str, args: dict, result: str) -> None:
        if tool_name not in _CACHEABLE_TOOLS:
            return
        ttl = _CACHEABLE_TOOLS[tool_name]
        key = self._make_key(tool_name, args)
        expires_at = time.monotonic() + ttl
        with self._lock:
            self._store[key] = (result, expires_at)
            self._store.move_to_end(key)
            while len(self._store) > _MAX_ENTRIES:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict:
        with self._lock:
            now = time.monotonic()
            total = len(self._store)
            live = sum(1 for _, (_, exp) in self._store.items() if exp > now)
            return {
                "total_entries": total,
                "live_entries": live,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / max(1, self._hits + self._misses), 3),
            }

    @staticmethod
    def _make_key(tool_name: str, args: dict) -> str:
        try:
            canonical = json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
        except Exception:
            canonical = str(sorted(args.items()))
        digest = hashlib.sha1(canonical.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"{tool_name}:{digest}"


_cache = ToolResultCache()


def get_tool_cache() -> ToolResultCache:
    return _cache
