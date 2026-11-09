"""In-memory TTL cache with SingleFlight / Thundering Herd protection for server queries."""

import asyncio
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple


class StatusCacheService:
    """Thread-safe / async-safe in-memory cache with SingleFlight lock per key."""

    def __init__(self, default_ttl_seconds: float = 30.0):
        self._default_ttl = default_ttl_seconds
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()
        self.hits = 0
        self.misses = 0

    async def _get_lock(self, key: str) -> asyncio.Lock:
        """Get or create an asyncio.Lock for a specific cache key."""
        async with self._master_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        ttl: Optional[float] = None,
        ttl_seconds: Optional[float] = None,
        force_refresh: bool = False,
    ) -> Any:
        """Return cached value if fresh, otherwise fetch via coroutine with SingleFlight protection."""
        effective_ttl = ttl_seconds if ttl_seconds is not None else (ttl if ttl is not None else self._default_ttl)
        now = time.monotonic()

        # Fast path: check without acquiring key lock
        if not force_refresh and key in self._cache:
            data, expires_at = self._cache[key]
            if now < expires_at:
                self.hits += 1
                return data

        # Slow path: acquire key lock to prevent Thundering Herd
        key_lock = await self._get_lock(key)
        async with key_lock:
            now = time.monotonic()
            # Double-check inside lock
            if not force_refresh and key in self._cache:
                data, expires_at = self._cache[key]
                if now < expires_at:
                    self.hits += 1
                    return data

            # Cache miss: fetch fresh data
            self.misses += 1
            result = await fetch_fn()
            # Store in cache
            self._cache[key] = (result, now + effective_ttl)
            return result

    def invalidate(self, key: str) -> None:
        """Remove a key from cache."""
        self._cache.pop(key, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self.hits = 0
        self.misses = 0


# Global shared singleton cache instance
status_cache = StatusCacheService(default_ttl_seconds=30.0)
