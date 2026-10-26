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
