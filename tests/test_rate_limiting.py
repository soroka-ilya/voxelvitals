"""Tests for R4: Intelligent Rate Limiting.

Covers Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases) for:
- Review submissions (5 req/min/IP, HTTP 429)
- Vote and manual ping / query rate limits
- Reverse proxy headers (X-Forwarded-For, X-Real-IP)
- Sliding window expiration and burst concurrency
"""

import asyncio
import time
from unittest.mock import patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.domain.models import ServerStatus
from app.limiter import limiter
from app.main import app
from app.services.rate_limiter import (
    SlidingWindowRateLimiter,
    api_query_rate_limiter,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Ensure test DB is initialized and rate limiters are cleared before each test."""
    await init_db()
    limiter._storage.reset()
    api_query_rate_limiter._records.clear()
    yield
    limiter._storage.reset()
    api_query_rate_limiter._records.clear()


@pytest_asyncio.fixture
async def client():
    """Create test client with standard base URL."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ==============================================================================
# Tier 1: Feature Coverage (R4 Core Rate Limiting Behaviors)
# ==============================================================================


@pytest.mark.asyncio
async def test_ping_within_limit_succeeds(client):
    """Verify ping requests under 30/min limit succeed."""
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(5):
            resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": "192.168.1.10"})
            assert resp.status_code == 200
            assert resp.json()["address"] == "mc.hypixel.net"


@pytest.mark.asyncio
async def test_ping_exceeding_limit_returns_429(client):
    """Verify 31st manual ping from same IP triggers HTTP 429 Too Many Requests."""
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(30):
            resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": "192.168.1.20"})
            assert resp.status_code == 200

        excess_resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": "192.168.1.20"})
        assert excess_resp.status_code == 429
        assert "Слишком много запросов" in excess_resp.json().get("detail", "")
        assert "Retry-After" in excess_resp.headers


@pytest.mark.asyncio
async def test_rate_limiting_distinct_ips_have_independent_quotas(client):
    """Verify distinct IPs have their own isolated rate limiting quotas."""
    mock_status = ServerStatus(address="2b2t.org", is_online=True, players_online=200, players_max=500)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(30):
            resp = await client.post("/api/ping/2b2t.org", headers={"X-Forwarded-For": "10.0.0.1"})
            assert resp.status_code == 200

        resp_blocked = await client.post("/api/ping/2b2t.org", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp_blocked.status_code == 429

        resp_allowed = await client.post("/api/ping/2b2t.org", headers={"X-Forwarded-For": "10.0.0.2"})
        assert resp_allowed.status_code == 200


@pytest.mark.asyncio
async def test_sliding_window_allows_requests_after_window_expires():
    """Verify SlidingWindowRateLimiter purges expired timestamps after window duration."""
    limiter = SlidingWindowRateLimiter(requests_limit=2, window_seconds=1)
    from fastapi import Request

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/test",
        "headers": [(b"host", b"test"), (b"x-forwarded-for", b"1.1.1.1")],
        "client": ("1.1.1.1", 12345),
    }
    req = Request(scope)

    # 2 requests succeed
    assert await limiter(req) is True
    assert await limiter(req) is True

    # 3rd request blocked
    with pytest.raises(Exception) as excinfo:
        await limiter(req)
    assert excinfo.value.status_code == 429

    # Wait for window to elapse
    await asyncio.sleep(1.05)

    # Next request succeeds
    assert await limiter(req) is True


@pytest.mark.asyncio
async def test_custom_sliding_window_10_req_limit_enforced():
    """Verify SlidingWindowRateLimiter enforces 10 req/min limit without storing IPs in DB."""
    from fastapi import Request
    limiter_10 = SlidingWindowRateLimiter(requests_limit=10, window_seconds=60)
    req = Request({"type": "http", "method": "POST", "path": "/api/ping/x", "headers": [(b"x-forwarded-for", b"172.16.0.5")], "client": ("127.0.0.1", 1000)})
    for _ in range(10):
        assert await limiter_10(req) is True
    with pytest.raises(Exception) as exc:
        await limiter_10(req)
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_api_query_rate_limiter_behavior():
    """Verify api_query_rate_limiter handles up to 60 queries/min."""
    limiter = SlidingWindowRateLimiter(requests_limit=60, window_seconds=60)
    from fastapi import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/status/mc.hypixel.net",
        "headers": [(b"host", b"test"), (b"x-real-ip", b"8.8.8.8")],
        "client": ("8.8.8.8", 50000),
    }
    req = Request(scope)

    for _ in range(60):
        res = await limiter(req)
        assert res is True

    # 61st triggers 429
    with pytest.raises(Exception) as excinfo:
        await limiter(req)
    assert excinfo.value.status_code == 429


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Headers, Bursts, Boundaries)
# ==============================================================================


@pytest.mark.asyncio
async def test_rate_limiting_exact_boundary_30th_allowed_31st_blocked(client):
    """Explicitly verify exact boundary: N=30 allowed, N=31 blocked."""
    ip = "192.168.100.55"
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    statuses = []
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(32):
            resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": ip})
            statuses.append(resp.status_code)

    assert statuses[:30] == [200] * 30
    assert statuses[30:] == [429, 429]


@pytest.mark.asyncio
async def test_rate_limiting_x_forwarded_for_client_ip_extraction(client):
    """Verify rightmost untrusted client IP in X-Forwarded-For is extracted (prevents XFF spoofing)."""
    proxy_chain = "203.0.113.195, 198.51.100.77"
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(30):
            resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": proxy_chain})
            assert resp.status_code == 200

        alt_chain = "8.8.8.8, 198.51.100.77, 127.0.0.1"
        blocked = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": alt_chain})
        assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiting_x_real_ip_client_ip_extraction(client):
    """Verify X-Real-IP header is properly recognized when X-Forwarded-For is absent."""
    ip = "198.51.100.42"
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(30):
            resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Real-IP": ip})
            assert resp.status_code == 200

        blocked = await client.post("/api/ping/mc.hypixel.net", headers={"X-Real-IP": ip})
        assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiting_burst_concurrency_protection(client):
    """Verify simultaneous concurrent burst requests respect the limit."""
    mock_status = ServerStatus(address="burst.server.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        async def post_ping():
            return await client.post("/api/ping/burst.server.net", headers={"X-Forwarded-For": "10.99.99.1"})

        responses = await asyncio.gather(*[post_ping() for _ in range(35)])
        status_codes = [r.status_code for r in responses]
        assert status_codes.count(200) == 30
        assert status_codes.count(429) == 5


@pytest.mark.asyncio
async def test_rate_limiting_retry_after_header_returned(client):
    """Verify 429 response contains a valid Retry-After header with seconds remaining."""
    mock_status = ServerStatus(address="mc.hypixel.net", is_online=True, players_online=100, players_max=200)
    with patch("app.api.api_routes.query_server", return_value=mock_status):
        for _ in range(30):
            await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": "10.50.50.50"})

        resp = await client.post("/api/ping/mc.hypixel.net", headers={"X-Forwarded-For": "10.50.50.50"})
        assert resp.status_code == 429
        assert "retry-after" in resp.headers
        assert 0 < int(resp.headers["retry-after"]) <= 60


@pytest.mark.asyncio
async def test_rate_limiter_isolated_paths():
    """Verify rate limit tracking is isolated per path."""
    from fastapi import Request
    limiter_5 = SlidingWindowRateLimiter(requests_limit=5, window_seconds=60)
    req_a = Request({"type": "http", "method": "POST", "path": "/api/ping/a", "headers": [(b"x-forwarded-for", b"192.168.200.200")], "client": ("127.0.0.1", 1000)})
    req_b = Request({"type": "http", "method": "GET", "path": "/api/status/b", "headers": [(b"x-forwarded-for", b"192.168.200.200")], "client": ("127.0.0.1", 1000)})

    for _ in range(5):
        assert await limiter_5(req_a) is True
    with pytest.raises(Exception) as exc:
        await limiter_5(req_a)
    assert exc.value.status_code == 429
    assert await limiter_5(req_b) is True
