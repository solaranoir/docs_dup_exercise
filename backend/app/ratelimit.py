"""In-process sliding-window rate limits for login and uploads.

Sufficient for the single-instance demo deployment. Counters reset on restart and are not
shared between instances; use a shared store (e.g. Redis) before scaling out.
"""

import math
import threading
import time
from collections import defaultdict, deque
from functools import lru_cache

from fastapi import HTTPException, Request, status

from app.auth import CurrentUser
from app.config import get_settings


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, now: float | None = None) -> float | None:
        """Record a hit. Returns seconds to wait if over the limit, else None."""
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return hits[0] + self.window - now
            hits.append(now)
            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


@lru_cache
def login_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(get_settings().login_rate_limit_per_minute, 60)


@lru_cache
def upload_limiter() -> SlidingWindowLimiter:
    return SlidingWindowLimiter(get_settings().upload_rate_limit_per_minute, 60)


def _too_many(retry_after: float) -> HTTPException:
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "Too many requests. Please wait and try again.",
        headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
    )


def limit_login(request: Request) -> None:
    # Behind Render's proxy, uvicorn --proxy-headers sets client.host from X-Forwarded-For.
    client = request.client.host if request.client else "unknown"
    if (wait := login_limiter().hit(f"ip:{client}")) is not None:
        raise _too_many(wait)


def limit_uploads(user: CurrentUser) -> None:
    if (wait := upload_limiter().hit(f"user:{user.id}")) is not None:
        raise _too_many(wait)


def reset_limits() -> None:
    login_limiter().reset()
    upload_limiter().reset()
