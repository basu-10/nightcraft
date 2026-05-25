# run_queue.py — No-op stub.
#
# The original in-memory queue and background worker have been replaced with
# synchronous in-request execution (PythonAnywhere-compatible).  This stub
# keeps the import alive for any code that still references run_queue so that
# nothing breaks at import time.


class _NullQueue:
    """Stub that satisfies the run_queue interface with all no-ops."""

    def enqueue(self, run_id: str) -> int:
        return 0

    def dequeue_blocking(self) -> str:
        raise RuntimeError("Background worker has been removed; runs execute synchronously.")

    def dequeue_next(self) -> str | None:
        return None

    def remove(self, run_id: str) -> None:
        pass

    def position(self, run_id: str) -> int:
        return 0

    def snapshot(self) -> list[str]:
        return []


run_queue = _NullQueue()
