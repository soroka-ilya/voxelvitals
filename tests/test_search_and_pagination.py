"""Tests for smart search routing, search results page, and catalog pagination."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.services.alias_service import (
    check_search_route,
    get_catalog_page,
    search_servers_catalog,
)


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_check_search_route_exact():
    """Verify exact alias or domain returns direct routing."""
    route_type, addr = check_search_route("hypixel")
    assert route_type == "direct"
    assert addr == "mc.hypixel.net"

    route_type, addr = check_search_route("2b2t")
    assert route_type == "direct"
    assert addr == "2b2t.org"

    route_type, addr = check_search_route("mc.reallyworld.ru")
    assert route_type == "direct"
    assert addr == "mc.reallyworld.ru"

    route_type, addr = check_search_route("donutsmp.net:25565")
    assert route_type == "direct"
    assert addr == "donutsmp.net:25565"


def test_check_search_route_partial():
    """Verify partial or multi-match queries return search routing."""
    route_type, q = check_search_route("mine")
    assert route_type == "search"
    assert q == "mine"

    route_type, q = check_search_route("craft")
    assert route_type == "search"
    assert q == "craft"

    route_type, q = check_search_route("pvp")
    assert route_type == "search"
    assert q == "pvp"


def test_search_servers_catalog():
    """Verify searching catalog returns ranked matching servers."""
    results = search_servers_catalog("mine")
    assert len(results) >= 2
    addresses = [s["address"] for s in results]
    assert any("minemen.club" in a or "vimeworld" in a for a in addresses)


def test_get_catalog_page_pagination():
    """Verify server catalog page slicing returns 6 servers per page."""
    page_1, total_pages, total_count = get_catalog_page(page=1, page_size=6)
    assert len(page_1) == 6
    assert total_pages >= 2
    assert total_count >= 10

    page_2, total_pages, total_count = get_catalog_page(page=2, page_size=6)
    assert len(page_2) > 0
    # No duplicate servers across page 1 and page 2
    p1_addrs = {s["address"] for s in page_1}
    p2_addrs = {s["address"] for s in page_2}
    assert p1_addrs.isdisjoint(p2_addrs)


@pytest.mark.asyncio
async def test_search_endpoint_direct_redirect(client):
    """Verify GET /search with exact server query redirects directly to /server/{address}."""
    res = await client.get("/search?q=hypixel", follow_redirects=False)
    assert res.status_code in (302, 303, 307)
    assert res.headers["location"] == "/server/mc.hypixel.net"

    # Bedrock preservation on redirect
    res_bedrock = await client.get("/search?q=donutsmp&bedrock=true", follow_redirects=False)
    assert res_bedrock.status_code in (302, 303, 307)
    assert res_bedrock.headers["location"] == "/server/donutsmp.net?bedrock=true"


@pytest.mark.asyncio
async def test_search_endpoint_results_page(client):
    """Verify GET /search with partial query renders dedicated results page."""
    res = await client.get("/search?q=craft")
    assert res.status_code == 200
    assert "Результаты поиска" in res.text
    assert "craft" in res.text.lower()
    assert "CubeCraft" in res.text or "Wynncraft" in res.text


@pytest.mark.asyncio
async def test_homepage_catalog_closer_and_pagination(client):
    """Verify home page has tightened spacing and pagination elements."""
    res = await client.get("/")
    assert res.status_code == 200
    # Search skeleton block removed from homepage (preventing layout gap)
    assert 'id="search-skeleton"' not in res.text
    # Pagination controls present
    assert 'id="catalog-pagination"' in res.text
    assert "data-page-btn" in res.text
