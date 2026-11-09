"""Intelligent sliding-window in-memory rate limiter for FastAPI routes."""

import time
from collections import defaultdict
from typing import Dict, List
from fastapi import HTTPException, Request, status


class SlidingWindowRateLimiter:
    """Sliding-window IP rate limiter without external dependencies."""

    def __init__(self, requests_limit: int = 5, window_seconds: int = 60):
        self.limit = requests_limit
        self.window = window_seconds
        self._records: Dict[str, List[float]] = defaultdict(list)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client real IP handling reverse proxy headers."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    async def __call__(self, request: Request) -> bool:
        """FastAPI dependency evaluation."""
        ip = self._get_client_ip(request)
        path = request.url.path
        key = f"{ip}:{path}"
        now = time.monotonic()
        cutoff = now - self.window

        timestamps = self._records[key]
        # Filter out expired timestamps
        self._records[key] = [t for t in timestamps if t > cutoff]

        if len(self._records[key]) >= self.limit:
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
