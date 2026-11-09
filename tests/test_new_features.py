import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.services.cache_service import StatusCacheService
from app.services.probes_service import get_multi_region_probes
from app.services.rate_limiter import SlidingWindowRateLimiter
from app.repository import ServerRepository


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_cache_singleflight():
    """Verify that 100 concurrent requests trigger exactly 1 underlying fetch."""
    cache = StatusCacheService(default_ttl_seconds=10.0)
    fetch_count = 0

    async def expensive_fetch():
        nonlocal fetch_count
        fetch_count += 1
        await asyncio.sleep(0.05)
        return {"players": 42000}

    # Launch 50 concurrent calls to same key
    results = await asyncio.gather(*[
        cache.get_or_fetch("hypixel:java", expensive_fetch)
        for _ in range(50)
    ])

    assert fetch_count == 1
    assert all(r["players"] == 42000 for r in results)
    assert cache.hits == 49
    assert cache.misses == 1


@pytest.mark.asyncio
async def test_multi_region_probes():
    """Verify regional probes computation for MSK, FRA, and HEL."""
    probes = get_multi_region_probes("mc.hypixel.net", base_latency_ms=120.0, edition="java")
    assert len(probes) == 3

    hub_codes = [p["hub_code"] for p in probes]
    assert "MSK" in hub_codes
    assert "FRA" in hub_codes
    assert "HEL" in hub_codes

    msk_probe = next(p for p in probes if p["hub_code"] == "MSK")
    assert msk_probe["latency_ms"] == 120.0
    assert msk_probe["city"] == "Москва"
    assert "🇷🇺" in msk_probe["flag_emoji"]

    # Test CIS server direct latency from Moscow
    cis_probes = get_multi_region_probes("play.vimeworld.ru", base_latency_ms=18.0, edition="java")
    cis_msk = next(p for p in cis_probes if p["hub_code"] == "MSK")
    assert cis_msk["latency_ms"] == 18.0


@pytest.mark.asyncio
async def test_sliding_window_rate_limiter():
    """Verify rate limiter blocks when threshold exceeded."""
    from starlette.requests import Request
    from fastapi import HTTPException

    limiter = SlidingWindowRateLimiter(requests_limit=3, window_seconds=60)
    
    # Mock ASGI request
    def make_mock_request(ip="1.2.3.4"):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/reviews",
            "headers": [(b"x-forwarded-for", ip.encode("utf-8"))],
            "client": ("127.0.0.1", 12345),
        }
        return Request(scope)

    # First 3 allowed
    for _ in range(3):
        assert await limiter(make_mock_request()) is True

    # 4th blocked with 429
    with pytest.raises(HTTPException) as exc_info:
        await limiter(make_mock_request())
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


@pytest.mark.asyncio
async def test_peak_hall_of_fame_records():
    """Verify peak player records from repository."""
    repo = ServerRepository()
    hypixel_peak = await repo.get_server_peak("mc.hypixel.net")
    assert hypixel_peak is not None
    assert hypixel_peak["peak_players"] >= 200000
    assert "2021" in hypixel_peak["peak_date"]


@pytest.mark.asyncio
async def test_rate_limiting_endpoint(client):
    """Verify HTTP 429 response on review endpoint when rate limit is exceeded."""
    responses = []
    for i in range(7):
        resp = await client.post(
            "/api/reviews",
            json={
                "server_address": "mc.hypixel.net",
                "rating": 5,
                "comment": f"Super test review {i}",
                "author_name": "Tester",
            },
            headers={"X-Forwarded-For": "198.51.100.55"}
        )
        responses.append(resp.status_code)

    assert 429 in responses
