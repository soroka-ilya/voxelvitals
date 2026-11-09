"""Tests for R3: Status Caching with Thundering Herd / Single-Flight Protection.

Covers Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases).
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch
import pytest
from app.domain.models import ServerStatus
from app.services.cache_service import StatusCacheService, status_cache
from app.services.pinger import query_server


@pytest.fixture
def cache():
    """Create a fresh isolated StatusCacheService instance for testing."""
    return StatusCacheService(default_ttl_seconds=30.0)


# ==============================================================================
# Tier 1: Feature Coverage (R3 Core Behaviors)
# ==============================================================================


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_data_without_refetch(cache):
    """Verify that a second fetch for the same key within TTL returns cached data."""
    fetch_mock = AsyncMock(return_value={"status": "online", "players": 100})

    res1 = await cache.get_or_fetch("test:key", fetch_mock, ttl=30.0)
    assert res1 == {"status": "online", "players": 100}
    assert fetch_mock.call_count == 1
    assert cache.misses == 1
    assert cache.hits == 0

    res2 = await cache.get_or_fetch("test:key", fetch_mock, ttl=30.0)
    assert res2 == {"status": "online", "players": 100}
    assert fetch_mock.call_count == 1  # Not called again
    assert cache.hits == 1
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_cache_miss_executes_fetch_fn_and_stores_result(cache):
    """Verify that a cache miss calls the fetch function and stores value."""
    fetch_mock = AsyncMock(return_value="fresh_value")

    result = await cache.get_or_fetch("missing:key", fetch_mock, ttl=10.0)
    assert result == "fresh_value"
    assert fetch_mock.call_count == 1
    assert "missing:key" in cache._cache


@pytest.mark.asyncio
async def test_cache_ttl_expiration_triggers_refetch(cache):
    """Verify that after TTL expires, fetch function is executed again."""
    fetch_mock = AsyncMock(side_effect=["first_result", "second_result"])

    res1 = await cache.get_or_fetch("expiring:key", fetch_mock, ttl=0.05)
    assert res1 == "first_result"

    await asyncio.sleep(0.08)

    res2 = await cache.get_or_fetch("expiring:key", fetch_mock, ttl=0.05)
    assert res2 == "second_result"
    assert fetch_mock.call_count == 2
    assert cache.misses == 2


@pytest.mark.asyncio
async def test_cache_force_refresh_bypasses_cache_even_if_fresh(cache):
    """Verify force_refresh=True always bypasses cache and re-fetches."""
    fetch_mock = AsyncMock(side_effect=["val1", "val2"])

    res1 = await cache.get_or_fetch("key", fetch_mock, ttl=60.0)
    assert res1 == "val1"

    res2 = await cache.get_or_fetch("key", fetch_mock, ttl=60.0, force_refresh=True)
    assert res2 == "val2"
    assert fetch_mock.call_count == 2


@pytest.mark.asyncio
async def test_cache_invalidate_removes_specific_key(cache):
    """Verify invalidate() removes only the target key from cache."""
    await cache.get_or_fetch("key1", AsyncMock(return_value="data1"), ttl=60.0)
    await cache.get_or_fetch("key2", AsyncMock(return_value="data2"), ttl=60.0)

    cache.invalidate("key1")

    assert "key1" not in cache._cache
    assert "key2" in cache._cache


@pytest.mark.asyncio
async def test_cache_clear_resets_all_entries_and_counters(cache):
    """Verify clear() purges all cache entries and resets hit/miss counters."""
    await cache.get_or_fetch("k1", AsyncMock(return_value="v1"), ttl=60.0)
    await cache.get_or_fetch("k1", AsyncMock(return_value="v1"), ttl=60.0)
    assert cache.hits == 1
    assert cache.misses == 1

    cache.clear()
    assert len(cache._cache) == 0
    assert cache.hits == 0
    assert cache.misses == 0


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Single-Flight, Locks, Edge Conditions)
# ==============================================================================


@pytest.mark.asyncio
async def test_singleflight_concurrent_thundering_herd_lock(cache):
    """Verify single-flight lock ensures fetch_fn runs exactly ONCE under 25 concurrent requests."""
    call_count = 0

    async def slow_fetch():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.04)
        return "singleflight_payload"

    # Launch 25 concurrent tasks requesting the same key simultaneously
    tasks = [
        cache.get_or_fetch("herd:key", slow_fetch, ttl=30.0)
        for _ in range(25)
    ]
    results = await asyncio.gather(*tasks)

    # All 25 callers received the exact same result
    assert len(results) == 25
    assert all(r == "singleflight_payload" for r in results)
    # The expensive fetch function ran only ONCE
    assert call_count == 1
    # 1 cache miss + 24 cache hits (thundering herd successfully absorbed)
    assert cache.misses == 1
    assert cache.hits == 24


@pytest.mark.asyncio
async def test_singleflight_different_keys_execute_concurrently(cache):
    """Verify separate keys use distinct locks and do not serialize each other."""
    started = []
    finished = []

    async def fetch_task(key_id: int):
        started.append(key_id)
        await asyncio.sleep(0.03)
        finished.append(key_id)
        return f"result_{key_id}"

    tasks = [
        cache.get_or_fetch(f"independent_key_{i}", lambda i=i: fetch_task(i), ttl=30.0)
        for i in range(5)
    ]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    assert len(started) == 5
    assert len(finished) == 5


@pytest.mark.asyncio
async def test_singleflight_fetch_failure_propagates_and_releases_lock(cache):
    """Verify that if fetch_fn raises an exception, lock is cleanly released without poisoning cache."""
    failing_fetch = AsyncMock(side_effect=RuntimeError("Upstream socket error"))

    with pytest.raises(RuntimeError, match="Upstream socket error"):
        await cache.get_or_fetch("failing:key", failing_fetch, ttl=30.0)

    # Failed result is not saved in cache
    assert "failing:key" not in cache._cache

    # Subsequent request does not hang and can succeed
    recovery_fetch = AsyncMock(return_value="recovered")
    recovered = await cache.get_or_fetch("failing:key", recovery_fetch, ttl=30.0)
    assert recovered == "recovered"


@pytest.mark.asyncio
async def test_cache_zero_or_negative_ttl_expires_immediately(cache):
    """Verify that zero or negative TTL expires immediately on next call."""
    fetch_mock = AsyncMock(side_effect=["val_a", "val_b"])

    res1 = await cache.get_or_fetch("zero_ttl", fetch_mock, ttl=0.0)
    assert res1 == "val_a"

    res2 = await cache.get_or_fetch("zero_ttl", fetch_mock, ttl=0.0)
    assert res2 == "val_b"
    assert fetch_mock.call_count == 2


@pytest.mark.asyncio
async def test_query_server_integration_uses_status_cache():
    """Verify query_server() integrates with status_cache to avoid redundant backend pings."""
    status_cache.clear()
    dummy_status = ServerStatus(
        address="cached.server.net",
        is_online=True,
        edition="java",
        players_online=42,
        players_max=100,
        latency_ms=15.0,
    )

    with patch("app.services.pinger._execute_query", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = dummy_status

        # First call: cache miss, invokes _execute_query
        res1 = await query_server("cached.server.net")
        assert res1.players_online == 42
        assert mock_exec.call_count == 1

        # Second call: within 30s TTL, served from cache
        res2 = await query_server("cached.server.net")
        assert res2.players_online == 42
        assert mock_exec.call_count == 1  # No second backend query

        # Force refresh: bypasses cache
        res3 = await query_server("cached.server.net", force_refresh=True)
        assert res3.players_online == 42
        assert mock_exec.call_count == 2


@pytest.mark.asyncio
async def test_query_server_java_and_bedrock_keys_are_isolated():
    """Verify Bedrock and Java editions maintain isolated cache keys for the same address."""
    status_cache.clear()
    java_status = ServerStatus(address="dual.server.net", is_online=True, edition="java", players_online=10)
    bedrock_status = ServerStatus(address="dual.server.net", is_online=True, edition="bedrock", players_online=20)

    with patch("app.services.pinger._execute_query", new_callable=AsyncMock) as mock_exec:
        mock_exec.side_effect = [java_status, bedrock_status]

        res_java = await query_server("dual.server.net", is_bedrock=False)
        res_bedrock = await query_server("dual.server.net", is_bedrock=True)

        assert res_java.edition == "java"
        assert res_java.players_online == 10
        assert res_bedrock.edition == "bedrock"
        assert res_bedrock.players_online == 20
        assert mock_exec.call_count == 2
