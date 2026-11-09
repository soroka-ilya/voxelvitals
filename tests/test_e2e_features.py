"""Tier 3 (Cross-Feature Combinations) & Tier 4 (Real-World Scenarios) E2E Tests.

Tests pairwise feature interactions and end-to-end multi-client application workflows:
- High concurrency status flood (F1 x F3)
- Telemetry polling and peak online tracking with multi-region probes (F2 x F5)
- Malicious spam attack with rate limiting and cache resilience (F3 x F4)
- Live client session SSE streaming with peak records (F1 x F5)
- Unreachable server probe handling and negative caching (F2 x F3)
"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.domain.models import ServerStatus
from app.main import app
from app.repository import ServerRepository
from app.services.cache_service import status_cache
from app.services.probes_service import get_multi_region_probes
from app.services.rate_limiter import review_rate_limiter, vote_rate_limiter



class CompatibleProbe(dict):
    """Dictionary supporting both direct key access and .to_dict() method."""
    def to_dict(self):
        return dict(self)


SAMPLE_PROBES = [
    CompatibleProbe({"code": "MSK", "city": "Москва", "country": "Россия", "flag": "🇷🇺", "latency_ms": 25.0, "status": "excellent"}),
    CompatibleProbe({"code": "FRA", "city": "Франкфурт", "country": "Германия", "flag": "🇩🇪", "latency_ms": 15.0, "status": "excellent"}),
    CompatibleProbe({"code": "HEL", "city": "Хельсинки", "country": "Финляндия", "flag": "🇫🇮", "latency_ms": 22.0, "status": "excellent"}),
]

orig_sleep = asyncio.sleep


async def bounded_sleep(sec, *args, **kwargs):
    if sec and sec > 0.05:
        raise asyncio.CancelledError()
    return await orig_sleep(sec, *args, **kwargs)


@pytest_asyncio.fixture(autouse=True)
async def setup_test_environment():
    """Reset database, cache, and rate limiters before each scenario."""
    await init_db()
    status_cache.clear()
    review_rate_limiter._records.clear()
    vote_rate_limiter._records.clear()
    yield
    status_cache.clear()
    review_rate_limiter._records.clear()
    vote_rate_limiter._records.clear()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def repo():
    return ServerRepository()


# ==============================================================================
# Tier 3: Pairwise Cross-Feature Interactions
# ==============================================================================


@pytest.mark.asyncio
async def test_cross_caching_and_realtime_sse(client):
    """Pairwise F1 x F3: Verify multiple concurrent SSE streams leverage caching."""
    mock_status = ServerStatus(
        address="shared.stream.net",
        is_online=True,
        edition="java",
        players_online=950,
        players_max=2000,
        latency_ms=22.0,
    )

    with patch("asyncio.sleep", side_effect=bounded_sleep), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES), \
         patch("app.services.pinger._execute_query", new_callable=AsyncMock, return_value=mock_status) as mock_exec:

        async def read_stream():
            async with client.stream("GET", "/api/live/shared.stream.net?interval=3") as resp:
                assert resp.status_code == 200
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        return json.loads(line[len("data: "):])

        # 3 clients connect to SSE stream simultaneously
        results = await asyncio.gather(read_stream(), read_stream(), read_stream())
        assert len(results) == 3
        assert all(r["players_online"] == 950 for r in results)
        # Status cache SingleFlight ensured backend pinger was called only ONCE
        assert mock_exec.call_count == 1


@pytest.mark.asyncio
async def test_cross_peak_online_and_multi_region_probes(repo):
    """Pairwise F2 x F5: Recording higher player peak calculates matching regional probes."""
    addr = f"peak.probes.{uuid.uuid4().hex[:8]}.ru"

    server_id = await repo.get_or_create_server(addr)

    # Spike in players records all-time peak
    spike_status = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=18500,
        players_max=25000,
        latency_ms=18.0,
    )
    await repo.record_telemetry(server_id, spike_status)

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 18500

    # Regional probes computed for this server reflect CIS low-latency route
    probes = get_multi_region_probes(addr, base_latency_ms=spike_status.latency_ms)
    p_map = {p["code"]: p["latency_ms"] for p in probes}
    assert p_map["MSK"] == 18.0
    assert p_map["FRA"] > p_map["MSK"]


@pytest.mark.asyncio
async def test_cross_caching_and_rate_limiting(client):
    """Pairwise F3 x F4: Status caching shields backend while rate limiter protects reviews."""
    ip = "192.168.10.99"
    # Submit 5 reviews to reach rate limit
    for i in range(5):
        r = await client.post(
            "/api/reviews",
            json={"server_address": "mc.hypixel.net", "rating": 5, "comment": f"Good server {i}"},
            headers={"X-Forwarded-For": ip},
        )
        assert r.status_code == 200

    # 6th review gets 429
    r_spam = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Spam"},
        headers={"X-Forwarded-For": ip},
    )
    assert r_spam.status_code == 429

    # Meanwhile, status queries continue to be served from cache safely
    status_resp = await client.get("/api/status/mc.hypixel.net?mock=true")
    assert status_resp.status_code == 200
    assert status_resp.json()["address"] == "mc.hypixel.net"


@pytest.mark.asyncio
async def test_cross_peak_online_and_rate_limiting(client, repo):
    """Pairwise F4 x F5: Blocked review spammers cannot pollute or mutate peak online records."""
    addr = f"protected.server.{uuid.uuid4().hex[:8]}.net"

    server_id = await repo.get_or_create_server(addr)

    # Establish initial legitimate peak
    legit_status = ServerStatus(address=addr, is_online=True, edition="java", players_online=5000)
    await repo.record_telemetry(server_id, legit_status)

    spammer_ip = "192.168.66.77"
    # Spammer hits review endpoint repeatedly
    for _ in range(7):
        await client.post(
            "/api/reviews",
            json={"server_address": addr, "rating": 1, "comment": "Trolling review spam attempt"},
            headers={"X-Forwarded-For": spammer_ip},
        )

    # Peak online records remained untampered
    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 5000


@pytest.mark.asyncio
async def test_cross_multi_region_probes_and_caching():
    """Pairwise F2 x F3: Cached server status consistently yields deterministic probe latencies."""
    status_cache.clear()
    server_addr = "cached.probes.net"
    cached_status = ServerStatus(
        address=server_addr,
        is_online=True,
        edition="java",
        players_online=1000,
        latency_ms=30.0,
    )

    with patch("app.services.pinger._execute_query", new_callable=AsyncMock, return_value=cached_status) as mock_exec:
        from app.services.pinger import query_server

        s1 = await query_server(server_addr)
        probes1 = get_multi_region_probes(server_addr, base_latency_ms=s1.latency_ms)

        s2 = await query_server(server_addr)
        probes2 = get_multi_region_probes(server_addr, base_latency_ms=s2.latency_ms)

        assert mock_exec.call_count == 1  # Cache preserved
        assert [p["latency_ms"] for p in probes1] == [p["latency_ms"] for p in probes2]
        assert [p["status"] for p in probes1] == [p["status"] for p in probes2]


# ==============================================================================
# Tier 4: Real-World Application Scenarios (TEST_INFRA.md Workloads)
# ==============================================================================


@pytest.mark.asyncio
async def test_scenario_1_high_concurrency_status_flood():
    """Scenario 1: 50 simultaneous clients fetching same server; SingleFlight allows 1 backend ping."""
    status_cache.clear()
    server_addr = "flood.target.org"
    mock_payload = ServerStatus(
        address=server_addr,
        is_online=True,
        edition="java",
        players_online=3400,
        players_max=10000,
        latency_ms=18.5,
    )

    fetch_counter = 0

    async def slow_backend_fetch():
        nonlocal fetch_counter
        fetch_counter += 1
        await asyncio.sleep(0.04)
        return mock_payload

    # 50 simultaneous incoming requests
    tasks = [
        status_cache.get_or_fetch(f"{server_addr}:java", slow_backend_fetch, ttl=30.0)
        for _ in range(50)
    ]
    results = await asyncio.gather(*tasks)

    assert len(results) == 50
    assert all(r.players_online == 3400 for r in results)
    # Critical SingleFlight contract: backend query executed exactly once
    assert fetch_counter == 1
    assert status_cache.misses == 1
    assert status_cache.hits == 49


@pytest.mark.asyncio
async def test_scenario_2_telemetry_polling_new_all_time_peak(repo):
    """Scenario 2: Telemetry polling records new all-time peak with regional latency distribution."""
    addr = f"record.breaker.{uuid.uuid4().hex[:8]}.net"

    server_id = await repo.get_or_create_server(addr)

    # Initial standard telemetry
    t1 = ServerStatus(address=addr, is_online=True, edition="java", players_online=5000, latency_ms=20.0)
    await repo.record_telemetry(server_id, t1)

    peak_initial = await repo.get_server_peak(addr)
    assert peak_initial["peak_players"] == 5000

    # Massive holiday spike arrives
    t2 = ServerStatus(address=addr, is_online=True, edition="java", players_online=28500, latency_ms=22.0)
    await repo.record_telemetry(server_id, t2)

    peak_updated = await repo.get_server_peak(addr)
    assert peak_updated["peak_players"] == 28500
    assert peak_updated["peak_date"] != ""

    # Multi-region probes calculated accurately
    probes = get_multi_region_probes(addr, base_latency_ms=t2.latency_ms)
    assert len(probes) == 3
    for p in probes:
        assert p["latency_ms"] > 0
        assert p["code"] in ["MSK", "FRA", "HEL"]


@pytest.mark.asyncio
async def test_scenario_3_malicious_review_spam_attack(client):
    """Scenario 3: Malicious script sends 20 rapid reviews from single IP; exactly 5 pass, 15 get 429."""
    attacker_ip = "185.220.101.5"

    responses = []
    for i in range(20):
        resp = await client.post(
            "/api/reviews",
            json={
                "server_address": "mc.hypixel.net",
                "rating": 1,
                "comment": f"Automated DDoS spam review payload #{i}",
            },
            headers={"X-Forwarded-For": attacker_ip},
        )
        responses.append(resp.status_code)

    # Exactly first 5 accepted, all remaining 15 blocked with 429
    assert responses[:5] == [200, 200, 200, 200, 200]
    assert responses[5:] == [429] * 15

    # Innocent user from separate IP is unaffected
    legit_resp = await client.post(
        "/api/reviews",
        json={
            "server_address": "mc.hypixel.net",
            "rating": 5,
            "comment": "Legitimate honest review from another user",
        },
        headers={"X-Forwarded-For": "93.184.216.34"},
    )
    assert legit_resp.status_code == 200


@pytest.mark.asyncio
async def test_scenario_4_active_client_session_sse_streaming(client, repo):
    """Scenario 4: Active client session receives live SSE stream and renders peak record."""
    addr = f"live.client.{uuid.uuid4().hex[:8]}.org"

    server_id = await repo.get_or_create_server(addr)

    # Prime historical peak in database
    seed_status = ServerStatus(address=addr, is_online=True, edition="java", players_online=45000)
    await repo.record_telemetry(server_id, seed_status)

    mock_live = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=38000,
        players_max=50000,
        latency_ms=19.5,
    )

    with patch("asyncio.sleep", side_effect=bounded_sleep), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES), \
         patch("app.services.pinger._execute_query", new_callable=AsyncMock, return_value=mock_live):

        async with client.stream("GET", f"/api/live/{addr}?interval=3") as resp:
            assert resp.status_code == 200
            payload = None
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[len("data: "):])
                    break

            assert payload is not None
            assert payload["address"] == addr
            assert payload["is_online"] is True
            assert payload["players_online"] == 38000
            assert len(payload["probes"]) == 3

        # Confirm peak record preserved in repository
        peak = await repo.get_server_peak(addr)
        assert peak["peak_players"] == 45000


@pytest.mark.asyncio
async def test_scenario_5_unreachable_server_probes_and_cache_resilience():
    """Scenario 5: Offline server negative probe handling and cache resilience."""
    status_cache.clear()
    offline_addr = "dead.minecraft.net"

    offline_status = ServerStatus(
        address=offline_addr,
        is_online=False,
        edition="java",
        players_online=0,
        players_max=0,
        latency_ms=0.0,
        error_message="Host unreachable (ETIMEDOUT)",
    )

    call_count = 0

    async def mock_network_query():
        nonlocal call_count
        call_count += 1
        return offline_status

    # Initial query encounters dead server
    s1 = await status_cache.get_or_fetch(f"{offline_addr}:java", mock_network_query, ttl=30.0)
    assert s1.is_online is False
    assert call_count == 1

    # Regional probes for offline host clamp safely to minimum without error
    probes = get_multi_region_probes(offline_addr, base_latency_ms=s1.latency_ms)
    assert len(probes) == 3
    for p in probes:
        assert p["latency_ms"] >= 1.0

    # Repeat query within 30s is served instantly from cache without hanging
    s2 = await status_cache.get_or_fetch(f"{offline_addr}:java", mock_network_query, ttl=30.0)
    assert s2.is_online is False
    assert call_count == 1  # No repeated network timeout
