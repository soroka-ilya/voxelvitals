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
from app.main import app
from app.services.rate_limiter import (
    SlidingWindowRateLimiter,
    api_query_rate_limiter,
    review_rate_limiter,
    vote_rate_limiter,
)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Ensure test DB is initialized and rate limiters are cleared before each test."""
    await init_db()
    review_rate_limiter._records.clear()
    vote_rate_limiter._records.clear()
    api_query_rate_limiter._records.clear()
    yield
    review_rate_limiter._records.clear()
    vote_rate_limiter._records.clear()
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
async def test_review_submission_within_limit_succeeds(client):
    """Verify up to 5 review submissions from one IP succeed within 1 minute."""
    for i in range(5):
        resp = await client.post(
            "/api/reviews",
            json={
                "server_address": "mc.hypixel.net",
                "rating": 5,
                "comment": f"Valid review comment #{i} here",
                "author_name": f"Tester_{i}",
            },
            headers={"X-Forwarded-For": "192.168.1.10"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["server_address"] == "mc.hypixel.net"
        assert data["rating"] == 5


@pytest.mark.asyncio
async def test_review_submission_6th_exceeding_limit_returns_429(client):
    """Verify 6th review submission from same IP triggers HTTP 429 Too Many Requests."""
    for i in range(5):
        resp = await client.post(
            "/api/reviews",
            json={
                "server_address": "mc.hypixel.net",
                "rating": 4,
                "comment": f"Legitimate review #{i}",
            },
            headers={"X-Forwarded-For": "192.168.1.20"},
        )
        assert resp.status_code == 200

    # 6th request from same IP must be rejected with 429
    excess_resp = await client.post(
        "/api/reviews",
        json={
            "server_address": "mc.hypixel.net",
            "rating": 1,
            "comment": "Spam attack review attempt #6",
        },
        headers={"X-Forwarded-For": "192.168.1.20"},
    )
    assert excess_resp.status_code == 429
    assert "Слишком много запросов" in excess_resp.json().get("detail", "")
    assert "Retry-After" in excess_resp.headers


@pytest.mark.asyncio
async def test_rate_limiting_distinct_ips_have_independent_quotas(client):
    """Verify distinct IPs have their own isolated rate limiting quotas."""
    # IP 10.0.0.1 exhausts all 5 requests
    for i in range(5):
        resp = await client.post(
            "/api/reviews",
            json={"server_address": "2b2t.org", "rating": 5, "comment": f"Review {i}"},
            headers={"X-Forwarded-For": "10.0.0.1"},
        )
        assert resp.status_code == 200

    # 6th from IP 10.0.0.1 gets 429
    resp_blocked = await client.post(
        "/api/reviews",
        json={"server_address": "2b2t.org", "rating": 5, "comment": "Spam"},
        headers={"X-Forwarded-For": "10.0.0.1"},
    )
    assert resp_blocked.status_code == 429

    # IP 10.0.0.2 can still submit its own 5 requests normally
    resp_allowed = await client.post(
        "/api/reviews",
        json={"server_address": "2b2t.org", "rating": 5, "comment": "Review from IP 2"},
        headers={"X-Forwarded-For": "10.0.0.2"},
    )
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
async def test_vote_rate_limiter_limit_enforced(client):
    """Verify vote endpoint enforces rate limit (10 req/min)."""
    # 10 vote attempts
    for i in range(10):
        resp = await client.post(
            "/api/vote",
            json={"server_address": f"server{i}.net"},
            headers={"X-Forwarded-For": "172.16.0.5"},
        )
        assert resp.status_code in [200, 400]

    # 11th request triggers rate limit 429
    resp_rate_limited = await client.post(
        "/api/vote",
        json={"server_address": "server_overflow.net"},
        headers={"X-Forwarded-For": "172.16.0.5"},
    )
    assert resp_rate_limited.status_code == 429


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
async def test_rate_limiting_exact_boundary_5th_allowed_6th_blocked(client):
    """Explicitly verify off-by-one boundary: N=5 allowed, N=6 blocked."""
    ip = "192.168.100.55"
    statuses = []
    for i in range(7):
        resp = await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": f"Boundary comment {i}"},
            headers={"X-Forwarded-For": ip},
        )
        statuses.append(resp.status_code)

    assert statuses == [200, 200, 200, 200, 200, 429, 429]


@pytest.mark.asyncio
async def test_rate_limiting_x_forwarded_for_client_ip_extraction(client):
    """Verify first IP in comma-separated X-Forwarded-For is extracted correctly."""
    proxy_chain = "203.0.113.195, 70.41.3.18, 150.172.238.178"
    for _ in range(5):
        resp = await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Valid comment"},
            headers={"X-Forwarded-For": proxy_chain},
        )
        assert resp.status_code == 200

    # Request from same primary client IP via different proxy chain is counted under the same key
    alt_chain = "203.0.113.195, 198.51.100.1"
    blocked = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Blocked comment"},
        headers={"X-Forwarded-For": alt_chain},
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiting_x_real_ip_client_ip_extraction(client):
    """Verify X-Real-IP header is properly recognized when X-Forwarded-For is absent."""
    ip = "198.51.100.42"
    for _ in range(5):
        resp = await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Valid comment"},
            headers={"X-Real-IP": ip},
        )
        assert resp.status_code == 200

    blocked = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Blocked"},
        headers={"X-Real-IP": ip},
    )
    assert blocked.status_code == 429


@pytest.mark.asyncio
async def test_rate_limiting_burst_concurrency_protection(client):
    """Verify simultaneous concurrent burst requests respect the limit."""
    async def post_review(idx: int):
        return await client.post(
            "/api/reviews",
            json={"server_address": "burst.server.net", "rating": 5, "comment": f"Burst review {idx}"},
            headers={"X-Forwarded-For": "10.99.99.1"},
        )

    responses = await asyncio.gather(*[post_review(i) for i in range(12)])
    status_codes = [r.status_code for r in responses]

    # Exactly 5 should be accepted (200), remaining 7 should be rejected (429)
    assert status_codes.count(200) == 5
    assert status_codes.count(429) == 7


@pytest.mark.asyncio
async def test_rate_limiting_retry_after_header_returned(client):
    """Verify 429 response contains a valid Retry-After header with seconds remaining."""
    for _ in range(5):
        await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Filler"},
            headers={"X-Forwarded-For": "10.50.50.50"},
        )

    resp = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Overflow"},
        headers={"X-Forwarded-For": "10.50.50.50"},
    )
    assert resp.status_code == 429
    assert "retry-after" in resp.headers
    retry_after = int(resp.headers["retry-after"])
    assert retry_after > 0 and retry_after <= 60


@pytest.mark.asyncio
async def test_rate_limiter_isolated_paths(client):
    """Verify rate limit tracking is isolated per path (reviews vs votes do not share bucket)."""
    ip = "192.168.200.200"

    # Exhaust review quota (5 reqs)
    for _ in range(5):
        await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Comment"},
            headers={"X-Forwarded-For": ip},
        )

    # 6th review gets 429
    resp_review_429 = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Blocked"},
        headers={"X-Forwarded-For": ip},
    )
    assert resp_review_429.status_code == 429

    # Vote endpoint for same IP is NOT blocked
    resp_vote = await client.post(
        "/api/vote",
        json={"server_address": "mc.hypixel.net"},
        headers={"X-Forwarded-For": ip},
    )
    assert resp_vote.status_code in [200, 400]
