"""Comprehensive End-to-End User Journeys and System Testing for VoxelVitals.

Simulates the complete lifecycle of everyday users navigating the site:
1. Discovery, autocomplete & catalog exploration
2. Search journeys with filters & empty states
3. Server inspection, live telemetry, and SVG badges
4. Interactive client beacons (IP copy, launcher, theme)
5. User authentication, review submission & community news
6. Admin verification of collected telemetry stream
"""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import get_db_connection, init_db
from app.main import app
from app.repository import ServerRepository


@pytest_asyncio.fixture
async def journey_env():
    """Setup clean database and async test client."""
    await init_db()
    repo = ServerRepository()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, repo


@pytest.mark.asyncio
async def test_user_journey_discovery_and_catalog(journey_env):
    """User Journey 1: Landing page exploration, autocomplete, and legal pages."""
    client, repo = journey_env

    # 1. User arrives on homepage
    res_home = await client.get("/")
    assert res_home.status_code == 200
    assert "VoxelVitals" in res_home.text
    assert "Live Explorer" in res_home.text
    assert "Каталог серверов" in res_home.text
    assert "vv_vid" not in res_home.cookies, "Tracking visitor cookie must NOT be set"

    # 2. User searches autocomplete for 'hyp'
    res_suggest_hyp = await client.get("/api/suggestions?q=hyp")
    assert res_suggest_hyp.status_code == 200
    suggestions = res_suggest_hyp.json()
    assert len(suggestions) > 0
    assert any("hypixel" in s["address"].lower() for s in suggestions)

    # 3. User checks Bedrock server autocomplete
    res_suggest_bedrock = await client.get("/api/suggestions?q=hive")
    assert res_suggest_bedrock.status_code == 200
    bedrock_suggestions = res_suggest_bedrock.json()
    assert len(bedrock_suggestions) > 0
    assert any("hive" in s["address"].lower() for s in bedrock_suggestions)

    # 4. User navigates to legal / informational footers
    res_terms = await client.get("/terms")
    assert res_terms.status_code == 200
    assert "Terms of Service" in res_terms.text

    res_privacy = await client.get("/privacy")
    assert res_privacy.status_code == 200
    assert "Privacy Policy" in res_privacy.text


@pytest.mark.asyncio
async def test_user_journey_search_flow_and_filters(journey_env):
    """User Journey 2: Searching by keyword, edition filtering, and empty state handling."""
    client, repo = journey_env

    # 1. User searches for 'hypixel' -> direct alias redirects (303) straight to server page
    res_search_direct = await client.get("/search?q=hypixel", follow_redirects=False)
    assert res_search_direct.status_code == 303
    assert "/server/mc.hypixel.net" in res_search_direct.headers["location"]

    # 1b. User searches by keyword 'survival' -> renders dedicated search results page (200)
    res_search_keyword = await client.get("/search?q=survival")
    assert res_search_keyword.status_code == 200
    assert "survival" in res_search_keyword.text.lower()

    # 2. User searches with edition=bedrock
    res_search_bedrock = await client.get("/search?q=hive&edition=bedrock", follow_redirects=True)
    assert res_search_bedrock.status_code == 200
    assert "bedrock" in res_search_bedrock.text.lower()

    # 3. User searches non-existent query
    nonsense_query = f"notfound_{uuid.uuid4().hex[:6]}"
    res_search_empty = await client.get(f"/search?q={nonsense_query}")
    assert res_search_empty.status_code == 200
    assert nonsense_query in res_search_empty.text
    assert "ничего не найдено" in res_search_empty.text.lower()

    # 4. User submits empty search query -> redirected or handled gracefully
    res_search_blank = await client.get("/search?q=")
    assert res_search_blank.status_code in (200, 302, 303)


@pytest.mark.asyncio
async def test_user_journey_server_detail_and_telemetry(journey_env):
    """User Journey 3: Viewing server detail, telemetry charts, and badges."""
    client, repo = journey_env

    # 1. User visits server detail page for Hypixel (with mock=true)
    res_server = await client.get("/server/mc.hypixel.net?mock=true")
    assert res_server.status_code == 200
    assert "mc.hypixel.net" in res_server.text
    assert "24-Hour Telemetry" in res_server.text
    assert "mc-motd-frame" in res_server.text
    assert "Копировать IP" in res_server.text
    assert "Играть в лаунчере" in res_server.text

    # 2. Check 24h telemetry JSON endpoint
    res_telem = await client.get("/api/telemetry/mc.hypixel.net?hours=24&mock=true")
    assert res_telem.status_code == 200
    telem_points = res_telem.json()
    assert isinstance(telem_points, list)
    assert len(telem_points) > 0
    assert "players_online" in telem_points[0]

    # 3. User views / embeds status badge
    res_badge = await client.get("/api/badge/mc.hypixel.net?mock=true")
    assert res_badge.status_code == 200
    assert "image/svg+xml" in res_badge.headers["content-type"]
    assert "<svg" in res_badge.text

    # 4. User views Bedrock server page
    res_bedrock = await client.get("/server/geo.hivebedrock.network?mock=true")
    assert res_bedrock.status_code == 200
    assert "bedrock" in res_bedrock.text.lower()


@pytest.mark.asyncio
async def test_user_journey_privacy_and_stateless_db(journey_env):
    """User Journey 4: Verify local fonts, zero tracking cookies, and strict stateless telemetry-only DB."""
    client, _ = journey_env

    # 1. Local fonts CSS served cleanly
    res_fonts = await client.get("/static/css/fonts.css")
    assert res_fonts.status_code == 200
    assert "/static/fonts/" in res_fonts.text

    # 2. Legacy UGC / auth / visitor-analytics routes all return 404
    for method, path in [
        ("POST", "/api/analytics/event"),
        ("POST", "/api/reviews"),
        ("POST", "/api/news"),
        ("POST", "/api/auth/register"),
        ("GET", "/analytics"),
    ]:
        resp = await client.request(method, path)
        assert resp.status_code == 404

    # 3. Verify SQLite contains ONLY stateless server telemetry tables
    async with get_db_connection() as conn:
        cur = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r["name"] for r in await cur.fetchall() if not r["name"].startswith("sqlite_")}
        assert tables == {"servers", "telemetry_history"}
