"""Intelligent sliding-window in-memory rate limiter for FastAPI routes."""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status
from app.limiter import get_real_client_ip


class SlidingWindowRateLimiter:
    """Sliding-window IP rate limiter with automatic memory cleanup."""

    def __init__(self, requests_limit: int = 5, window_seconds: int = 60):
        self.limit = requests_limit
        self.window = window_seconds
        self._records: Dict[str, List[float]] = defaultdict(list)
        self._last_cleanup = time.monotonic()

    def _cleanup_expired(self, now: float):
        """Purge keys whose timestamps are all expired to prevent memory growth."""
        cutoff = now - self.window
        expired_keys = [
            k for k, timestamps in self._records.items()
            if not timestamps or timestamps[-1] <= cutoff
        ]
        for k in expired_keys:
            del self._records[k]
        self._last_cleanup = now

    async def __call__(self, request: Request) -> bool:
        """FastAPI dependency evaluation."""
        ip = get_real_client_ip(request)
        path = request.url.path
        key = f"{ip}:{path}"
        now = time.monotonic()
        cutoff = now - self.window

        # Periodic cleanup every 100 requests or 60 seconds
        if now - self._last_cleanup > 60:
            self._cleanup_expired(now)

        timestamps = self._records[key]
        valid_timestamps = [t for t in timestamps if t > cutoff]
        self._records[key] = valid_timestamps

        if len(valid_timestamps) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Слишком много запросов (лимит: {self.limit} в {self.window} сек). Пожалуйста, подождите перед повторной отправкой.",
                headers={"Retry-After": str(self.window)},
            )

        self._records[key].append(now)
        return True


# Pre-configured rate limiters
review_rate_limiter = SlidingWindowRateLimiter(requests_limit=5, window_seconds=60)
vote_rate_limiter = SlidingWindowRateLimiter(requests_limit=10, window_seconds=60)
api_query_rate_limiter = SlidingWindowRateLimiter(requests_limit=60, window_seconds=60)
