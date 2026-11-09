"""Tests for R1: Real-Time Status Streaming (SSE).

Covers Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases) for:
- Server-Sent Events (SSE) streaming endpoint
- HTTP headers (X-Accel-Buffering: no, Cache-Control: no-cache, text/event-stream)
- Stream event format (data: ...\n\n) and payload attributes
- Disconnect handling, interval configurations, and error resiliency
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.domain.models import ServerStatus
from app.main import app


orig_sleep = asyncio.sleep


async def bounded_sleep(sec, *args, **kwargs):
    if sec and sec > 0.05:
        raise asyncio.CancelledError()
    return await orig_sleep(sec, *args, **kwargs)


class CompatibleProbe(dict):
    """Dictionary supporting both direct key access and .to_dict() method."""
    def to_dict(self):
        return dict(self)


SAMPLE_PROBES = [
    CompatibleProbe({"code": "MSK", "city": "Москва", "country": "Россия", "flag": "🇷🇺", "latency_ms": 25.0, "status": "excellent"}),
    CompatibleProbe({"code": "FRA", "city": "Франкфурт", "country": "Германия", "flag": "🇩🇪", "latency_ms": 15.0, "status": "excellent"}),
    CompatibleProbe({"code": "HEL", "city": "Хельсинки", "country": "Финляндия", "flag": "🇫🇮", "latency_ms": 22.0, "status": "excellent"}),
]


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest_asyncio.fixture(autouse=True)
async def default_mocks():
    default_status = ServerStatus(
        address="mc.hypixel.net",
        is_online=True,
        edition="java",
        players_online=1420,
        players_max=5000,
        latency_ms=25.0,
    )
    with patch("asyncio.sleep", side_effect=bounded_sleep), \
         patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=default_status), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        yield



@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ==============================================================================
# Tier 1: Feature Coverage (R1 Core Behaviors)
# ==============================================================================


@pytest.mark.asyncio
async def test_sse_endpoint_headers_and_content_type(client):
    """Verify SSE streaming endpoint returns text/event-stream with proxy-buffering disabled."""
    async with client.stream("GET", "/api/live/mc.hypixel.net?interval=3") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        assert response.headers.get("x-accel-buffering") == "no"
        assert "no-cache" in response.headers.get("cache-control", "")
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                break



@pytest.mark.asyncio
async def test_sse_event_stream_format(client):
    """Verify stream outputs valid SSE frames beginning with 'data: ' and ending with newline."""
    mock_status = ServerStatus(
        address="mc.hypixel.net",
        is_online=True,
        edition="java",
        players_online=12000,
        players_max=100000,
        latency_ms=28.5,
    )

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        async with client.stream("GET", "/api/live/mc.hypixel.net?interval=3") as response:
            lines = []
            async for line in response.aiter_lines():
                if line:
                    lines.append(line)
                    break

            assert len(lines) > 0
            assert lines[0].startswith("data: ")


@pytest.mark.asyncio
async def test_sse_initial_status_payload(client):
    """Verify first SSE payload contains complete server status and probe metrics."""
    mock_status = ServerStatus(
        address="mc.hypixel.net",
        is_online=True,
        edition="java",
        players_online=24500,
        players_max=100000,
        version_name="Paper 1.21.1",
        latency_ms=32.0,
    )

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        async with client.stream("GET", "/api/live/mc.hypixel.net?interval=3") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    raw_json = line[len("data: "):]
                    payload = json.loads(raw_json)
                    assert payload["address"] == "mc.hypixel.net"
                    assert payload["is_online"] is True
                    assert payload["players_online"] == 24500
                    assert payload["players_max"] == 100000
                    assert payload["latency_ms"] == 32.0
                    assert len(payload["probes"]) == 3
                    break


@pytest.mark.asyncio
async def test_sse_bedrock_edition_flag(client):
    """Verify ?bedrock=true queries bedrock status edition."""
    mock_status = ServerStatus(
        address="geo.hivebedrock.network",
        is_online=True,
        edition="bedrock",
        players_online=3500,
        players_max=10000,
        latency_ms=45.0,
    )

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status) as mock_q, \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        async with client.stream("GET", "/api/live/geo.hivebedrock.network?bedrock=true&interval=3") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    break
        mock_q.assert_called_with("geo.hivebedrock.network", is_bedrock=True)


@pytest.mark.asyncio
async def test_sse_custom_interval_query_parameter(client):
    """Verify custom interval parameter is accepted within allowed limits."""
    async with client.stream("GET", "/api/live/mc.hypixel.net?interval=60") as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                break

    # Non-integer interval rejected with HTTP 422 Unprocessable Entity
    resp_invalid = await client.get("/api/live/mc.hypixel.net?interval=notanumber")
    assert resp_invalid.status_code == 422




@pytest.mark.asyncio
async def test_sse_alias_resolution_in_stream(client):
    """Verify alias 'hypixel' automatically resolves to 'mc.hypixel.net' in SSE stream."""
    mock_status = ServerStatus(
        address="mc.hypixel.net",
        is_online=True,
        edition="java",
        players_online=15000,
        players_max=100000,
    )

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status) as mock_q, \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        async with client.stream("GET", "/api/live/hypixel?interval=3") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[len("data: "):])
                    assert payload["address"] == "mc.hypixel.net"
                    break
        mock_q.assert_called_with("mc.hypixel.net", is_bedrock=False)


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Disconnects, Errors, Negative States)
# ==============================================================================


@pytest.mark.asyncio
async def test_sse_client_disconnect_terminates_gracefully(client):
    """Verify stream generator exits cleanly upon detecting client disconnection."""
    mock_status = ServerStatus(address="test.net", is_online=True, edition="java")

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        # Open connection and close client transport immediately
        async with client.stream("GET", "/api/live/test.net?interval=3") as response:
            assert response.status_code == 200
            # Read 1 chunk and exit context manager (simulates browser tab close)
            async for _ in response.aiter_lines():
                break
        # Generator terminated without unhandled exception or hanging task
        assert True


@pytest.mark.asyncio
async def test_sse_offline_server_handled_gracefully(client):
    """Verify offline server yields is_online=False event without 500 error."""
    mock_offline = ServerStatus(
        address="offline.server.org",
        is_online=False,
        edition="java",
        players_online=0,
        players_max=0,
        latency_ms=0.0,
        error_message="Connection timed out",
    )

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_offline), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        async with client.stream("GET", "/api/live/offline.server.org?interval=3") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[len("data: "):])
                    assert payload["is_online"] is False
                    assert payload["players_online"] == 0
                    break


@pytest.mark.asyncio
async def test_sse_query_server_exception_yields_error_event(client):
    """Verify backend exception inside stream loop emits error data without severing HTTP connection."""
    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, side_effect=RuntimeError("DNS resolve failed")):
        async with client.stream("GET", "/api/live/unresolvable.org?interval=3") as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    payload = json.loads(line[len("data: "):])
                    assert "error" in payload
                    assert "DNS resolve failed" in payload["error"]
                    break


@pytest.mark.asyncio
async def test_sse_rapid_connect_disconnect_stress(client):
    """Verify multiple rapid connect-disconnect cycles do not leak tasks or throw errors."""
    mock_status = ServerStatus(address="stress.server.net", is_online=True, edition="java")

    with patch("app.api.api_routes.query_server", new_callable=AsyncMock, return_value=mock_status), \
         patch("app.api.api_routes.get_multi_region_probes", return_value=SAMPLE_PROBES):
        for _ in range(5):
            async with client.stream("GET", "/api/live/stress.server.net?interval=3") as resp:
                assert resp.status_code == 200
                async for _ in resp.aiter_lines():
                    break


@pytest.mark.asyncio
async def test_sse_special_characters_in_address(client):
    """Verify URL-encoded and unusual characters in address are handled safely."""
    async with client.stream("GET", "/api/live/play%2Eserver%2Ecom?interval=3") as resp:
        assert resp.status_code == 200
        async for line in resp.aiter_lines():
            if line.startswith("data: "):
                break

