"""
Small in-process rate limiter: sliding window of timestamps per key.
Single-process by design — matches the current one-instance deployment; swap
the storage for Redis when the app scales horizontally.
"""

import time
from collections import deque
from threading import Lock

from fastapi import HTTPException, Request

from app.core.config import settings


class SlidingWindowLimiter:
    def __init__(self, max_events: int, window_seconds: float):
        self.max_events = max_events
        self.window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            events = self._events.setdefault(key, deque())
            cutoff = now - self.window
            while events and events[0] < cutoff:
                events.popleft()
            if len(events) >= self.max_events:
                return False
            events.append(now)
            return True


auth_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_AUTH_PER_MINUTE, 60.0)
ask_limiter = SlidingWindowLimiter(settings.RATE_LIMIT_ASK_PER_MINUTE, 60.0)


def client_ip(request: Request) -> str:
    """Real client IP, honoring the reverse proxy's X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(limiter: SlidingWindowLimiter, key: str, detail: str) -> None:
    if not limiter.allow(key):
        raise HTTPException(status_code=429, detail=detail)
