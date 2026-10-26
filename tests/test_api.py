"""Integration tests for web routes, partials, and REST API."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_home_page(client):
    """Verify landing page renders successfully."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "VoxelVitals" in response.text
    assert "Live Explorer" in response.text


@pytest.mark.asyncio
async def test_server_detail_page(client):
    """Verify server detail page renders with mock telemetry."""
    response = await client.get("/server/mc.hypixel.net?mock=true")
    assert response.status_code == 200
    assert "mc.hypixel.net" in response.text
    assert "24-Hour Telemetry" in response.text


@pytest.mark.asyncio
async def test_api_status_endpoint(client):
    """Verify JSON REST API returns valid ServerStatus payload."""
    response = await client.get("/api/status/mc.hypixel.net?mock=true")
    assert response.status_code == 200
    data = response.json()
    assert data["address"] == "mc.hypixel.net"
    assert data["is_online"] is True
    assert data["players_online"] == 1420
    assert "motd_html" in data


@pytest.mark.asyncio
async def test_api_badge_endpoint(client):
    """Verify dynamic SVG badge endpoint returns correct SVG XML with headers."""
    response = await client.get("/api/badge/mc.hypixel.net.svg?mock=true")
    assert response.status_code == 200
    assert "image/svg+xml" in response.headers.get("content-type", "")
    assert "<svg" in response.text
    assert "mc.hypixel.net" in response.text


@pytest.mark.asyncio
async def test_htmx_partials(client):
    """Verify HTMX partial server card and skeleton components."""
    # Skeleton partial
    res_skel = await client.get("/partials/skeleton-card")
    assert res_skel.status_code == 200
    assert "skeleton-box" in res_skel.text

    # Server card partial
    res_card = await client.get("/partials/server-card?address=mc.hypixel.net&mock=true")
    assert res_card.status_code == 200
    assert "mc.hypixel.net" in res_card.text
    assert "Copy IP" in res_card.text


@pytest.mark.asyncio
async def test_legal_pages(client):
    """Verify Privacy Policy and Terms of Service render correctly."""
    res_privacy = await client.get("/privacy")
    assert res_privacy.status_code == 200
    assert "Privacy Policy" in res_privacy.text

    res_terms = await client.get("/terms")
    assert res_terms.status_code == 200
    assert "Terms of Service" in res_terms.text
