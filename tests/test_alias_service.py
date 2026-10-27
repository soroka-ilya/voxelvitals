"""Unit and integration tests for AliasService, address resolution, and suggestion API."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.services.alias_service import (
    get_curated_catalog,
    normalize_query,
    resolve_address,
    search_suggestions,
)


def test_alias_resolution_known_servers():
    """Verify alias mapping for all major Minecraft networks."""
    assert resolve_address("2b2t") == "2b2t.org"
    assert resolve_address("hypixel") == "mc.hypixel.net"
    assert resolve_address("cubecraft") == "play.cubecraft.net"
    assert resolve_address("donutsmp") == "donutsmp.net"
    assert resolve_address("wynncraft") == "play.wynncraft.com"
    assert resolve_address("minemen") == "minemen.club"
    assert resolve_address("gommehd") == "gommehd.net"
    assert resolve_address("manacube") == "play.manacube.com"
    assert resolve_address("vimeworld") == "mc.vimeworld.net"
    assert resolve_address("complex") == "hub.mc-complex.com"


def test_query_normalization_and_spaces():
    """Verify normalization of spaces, casing, and common keywords."""
    assert resolve_address("2b 2t") == "2b2t.org"
    assert resolve_address("  HYPIXEL  ") == "mc.hypixel.net"
    assert resolve_address("hypixel network") == "mc.hypixel.net"
    assert resolve_address("donut smp") == "donutsmp.net"
    assert resolve_address("wynn craft") == "play.wynncraft.com"
    assert resolve_address("cube craft") == "play.cubecraft.net"
    assert resolve_address("minemen club") == "minemen.club"
    assert resolve_address("gomme hd") == "gommehd.net"
    assert resolve_address("mana cube") == "play.manacube.com"
    assert resolve_address("vime world") == "mc.vimeworld.net"


def test_tld_fallback_for_unknown():
    """Verify fallback to .net when no domain extension is present."""
    assert resolve_address("unknowncraft") == "unknowncraft.net"
    assert resolve_address("myserver") == "myserver.net"
    # Existing domain should stay intact
    assert resolve_address("custom.domain.org") == "custom.domain.org"
    assert resolve_address("play.example.com") == "play.example.com"


def test_port_handling():
    """Verify port is preserved when resolving aliases or fallback."""
    assert resolve_address("hypixel:25565") == "mc.hypixel.net:25565"
    assert resolve_address("2b 2t:25565") == "2b2t.org:25565"
    assert resolve_address("myserver:19132") == "myserver.net:19132"


def test_empty_and_whitespace_resolution():
    """Verify empty or whitespace strings return empty string."""
    assert resolve_address("") == ""
    assert resolve_address("   ") == ""


def test_search_suggestions():
    """Verify search suggestions autocomplete functionality."""
    # Empty query should return curated suggestions
    empty_res = search_suggestions("", limit=5)
    assert len(empty_res) == 5
    assert "name" in empty_res[0]
    assert "address" in empty_res[0]
    assert "category" in empty_res[0]
    assert "icon" in empty_res[0]

    # Query matching hypixel
    hyp_res = search_suggestions("hyp")
    assert any("hypixel" in item["address"].lower() or "hypixel" in item["name"].lower() for item in hyp_res)

    # Query matching 2b2t
    anarchy_res = search_suggestions("2b")
    assert any("2b2t.org" in item["address"] for item in anarchy_res)


def test_curated_catalog_categories():
    """Verify curated catalog contains required genre tags and servers."""
    catalog = get_curated_catalog()
    assert len(catalog) >= 10

    categories = {s["category"] for s in catalog}
    assert "anarchy" in categories
    assert "minigames" in categories
    assert "rpg" in categories
    assert "pvp" in categories

    anarchy_servers = [s["address"] for s in catalog if s["category"] == "anarchy"]
    assert "2b2t.org" in anarchy_servers
    assert "donutsmp.net" in anarchy_servers

    minigames_servers = [s["address"] for s in catalog if s["category"] == "minigames"]
    assert "mc.hypixel.net" in minigames_servers
    assert "play.cubecraft.net" in minigames_servers
    assert "gommehd.net" in minigames_servers
    assert "mc.vimeworld.net" in minigames_servers

    rpg_servers = [s["address"] for s in catalog if s["category"] == "rpg"]
    assert "play.wynncraft.com" in rpg_servers
    assert "play.manacube.com" in rpg_servers

    pvp_servers = [s["address"] for s in catalog if s["category"] == "pvp"]
    assert "minemen.club" in pvp_servers


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_api_suggestions_endpoint(client):
    """Verify GET /api/suggestions returns matching suggestions."""
    response = await client.get("/api/suggestions?q=hyp")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert any("hypixel" in item["address"].lower() for item in data)


@pytest.mark.asyncio
async def test_server_route_resolves_alias(client):
    """Verify typing short alias in /server/{address} resolves to canonical domain."""
    response = await client.get("/server/2b2t?mock=true")
    assert response.status_code == 200
    assert "2b2t.org" in response.text


@pytest.mark.asyncio
async def test_partial_card_resolves_alias(client):
    """Verify typing short alias in /partials/server-card resolves to canonical domain."""
    response = await client.get("/partials/server-card?address=hypixel&mock=true")
    assert response.status_code == 200
    assert "mc.hypixel.net" in response.text


def test_suggestions_spaced_and_port_queries():
    """Verify autocomplete suggestions succeed for spaced queries and queries with ports."""
    res_2b = search_suggestions("2b 2t")
    assert any("2b2t.org" in item["address"] for item in res_2b)

    res_donut = search_suggestions("donut smp")
    assert any("donutsmp.net" in item["address"] for item in res_donut)

    res_gomme = search_suggestions("gomme hd")
    assert any("gommehd.net" in item["address"] for item in res_gomme)

    res_port = search_suggestions("mc.hypixel.net:25565")
    assert any("mc.hypixel.net" in item["address"] for item in res_port)


def test_localhost_and_ipv6_resolution():
    """Verify localhost is preserved without TLD fallback and IPv6 parsing is robust."""
    assert resolve_address("localhost") == "localhost"
    assert resolve_address("localhost:25565") == "localhost:25565"
    assert resolve_address("2001:db8::1234") == "2001:db8::1234"
    assert resolve_address("[2001:db8::1]:25565") == "[2001:db8::1]:25565"


def test_fallback_query_no_spaces():
    """Verify fallback TLD domain does not contain illegal spaces."""
    assert resolve_address("craft land") == "craftland.net"


@pytest.mark.asyncio
async def test_api_status_resolves_alias(client):
    """Verify /api/status/{address} resolves alias to canonical address."""
    response = await client.get("/api/status/2b2t?mock=true")
    assert response.status_code == 200
    data = response.json()
    assert data["address"] == "2b2t.org"


def test_expanded_servers_resolution():
    """Verify newly added popular CIS and worldwide servers resolve cleanly."""
    assert resolve_address("reallyworld") == "mc.reallyworld.ru"
    assert resolve_address("funtime") == "mc.funtime.su"
    assert resolve_address("holyworld") == "mc.holyworld.ru"
    assert resolve_address("hive") == "geo.hivebedrock.network"


def test_dynamic_fallback_suggestion():
    """Verify any arbitrary domain or query gets a valid dynamic suggestion."""
    res_custom = search_suggestions("mycustomserver.gg")
    assert len(res_custom) > 0
    assert any("mycustomserver.gg" in item["address"] for item in res_custom)

    res_unknown = search_suggestions("superunknownmine")
    assert len(res_unknown) > 0
    assert any("superunknownmine.net" in item["address"] for item in res_unknown)


@pytest.mark.asyncio
async def test_bedrock_flag_preservation(client):
    """Verify partial card preserves bedrock flag in links."""
    response = await client.get("/partials/server-card?address=donutsmp&bedrock=true&mock=true")
    assert response.status_code == 200
    assert "bedrock=true" in response.text


