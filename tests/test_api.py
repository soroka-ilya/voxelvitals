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
    """Verify landing page renders successfully with catalog and autocomplete."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "VoxelVitals" in response.text
    assert "Live Explorer" in response.text
    assert "Каталог серверов" in response.text
    assert "autocomplete-dropdown" in response.text
    assert "Копировать IP" in response.text
    assert "2b2t" in response.text
    assert "Hypixel" in response.text


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


@pytest.mark.asyncio
async def test_homepage_filter_toolbar_and_no_quicktest(client):
    """Verify homepage has advanced filter toolbar and no quick test chips."""
    response = await client.get("/")
    assert response.status_code == 200
    # Quick test section should be removed
    assert "Quick test:" not in response.text
    # Advanced filter toolbar should be present
    assert "edition-tab" in response.text
    assert "category-dropdown-btn" in response.text
    assert "version-dropdown-btn" in response.text
    assert "1.21.x Tricky Trials" in response.text
    assert "catalog-card-clickable" in response.text


@pytest.mark.asyncio
async def test_server_detail_bedrock_and_clean_players(client):
    """Verify server detail correctly handles Bedrock and has clean player samples."""
    # Test auto-detected Bedrock
    res_bedrock = await client.get("/server/hive?mock=true")
    assert res_bedrock.status_code == 200
    assert "bedrock" in res_bedrock.text.lower()

    # Test explicit Bedrock query on Java address
    res_donut_bedrock = await client.get("/server/donutsmp?bedrock=true&mock=true")
    assert res_donut_bedrock.status_code == 200
    assert "bedrock" in res_donut_bedrock.text.lower()

    # Test clean player sample (no 00000000... UUIDs)
    assert "00000000..." not in res_donut_bedrock.text
    assert "Активен" in res_donut_bedrock.text
    assert "mc-motd-frame" in res_donut_bedrock.text

