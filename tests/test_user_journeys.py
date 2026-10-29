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
from app.database import init_db
from app.main import app
from app.repository import ServerRepository
from app.services.auth_service import hash_password


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
    assert "vv_vid" in res_home.cookies, "Visitor cookie must be set on arrival"

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
async def test_user_journey_client_interaction_beacons(journey_env):
    """User Journey 4: Interactive client events (copy IP, launch client, toggle theme)."""
    client, repo = journey_env

    # 1. User clicks 'Копировать IP' -> beacon sent
    res_copy = await client.post(
        "/api/analytics/event",
        json={"event_type": "copy_ip", "target": "mc.hypixel.net", "metadata": {"source": "card"}},
    )
    assert res_copy.status_code == 200
    assert res_copy.json()["status"] == "ok"

    # 2. User clicks 'Запустить' client launcher -> beacon sent
    res_launch = await client.post(
        "/api/analytics/event",
        json={"event_type": "launch_client", "target": "mc.hypixel.net", "metadata": {"edition": "java"}},
    )
    assert res_launch.status_code == 200

    # 3. User toggles theme -> beacon sent
    res_theme = await client.post(
        "/api/analytics/event",
        json={"event_type": "toggle_theme", "target": "dark", "metadata": {}},
    )
    assert res_theme.status_code == 200

    # 4. Invalid event payload returns validation error (422)
    res_invalid = await client.post(
        "/api/analytics/event",
        json={"event_type": "", "target": ""},
    )
    assert res_invalid.status_code == 422


@pytest.mark.asyncio
async def test_user_journey_auth_reviews_and_community(journey_env):
    """User Journey 5: Account registration, login, server review & news creation."""
    client, repo = journey_env

    # 1. Unauthenticated review attempt should be rejected or require author
    res_unauth_rev = await client.post(
        "/api/reviews",
        json={"server_address": "mc.hypixel.net", "rating": 5, "comment": "Great server!"},
    )
    # If anonymous reviews are allowed, author defaults to 'Гость' or user name; let's check response
    assert res_unauth_rev.status_code in (200, 201, 401, 403)

    # 2. Register a new user
    uname = f"gamer_{uuid.uuid4().hex[:8]}"
    pwd = "SecretPassword123"
    res_reg = await client.post(
        "/api/auth/register",
        json={"username": uname, "password": pwd, "mc_nickname": "Steve_Pro"},
    )
    assert res_reg.status_code in (200, 201)

    # 3. Log in as registered user
    res_login = await client.post(
        "/api/auth/login",
        json={"username": uname, "password": pwd},
    )
    assert res_login.status_code == 200
    assert "session_token" in res_login.cookies
    client.cookies.update(res_login.cookies)

    # 4. Check user profile / auth status
    res_me = await client.get("/api/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["username"] == uname
    assert res_me.json()["mc_nickname"] == "Steve_Pro"

    # 5. Post server review as logged in user
    res_rev = await client.post(
        "/api/reviews",
        json={
            "server_address": "mc.hypixel.net",
            "rating": 5,
            "comment": "Отличный сервер, стабильный пинг и крутые мини-игры!",
        },
    )
    assert res_rev.status_code in (200, 201)

    # 6. Verify review appears in reviews list
    res_rev_list = await client.get("/api/reviews/mc.hypixel.net")
    assert res_rev_list.status_code == 200
    reviews = res_rev_list.json()
    assert any("Отличный сервер" in r.get("comment", "") for r in reviews)

    # 7. Post server news
    res_news = await client.post(
        "/api/news",
        json={
            "server_address": "mc.hypixel.net",
            "title": "Праздничный турнир BedWars",
            "content": "В эту субботу пройдет турнир с призами для всех участников!",
            "tag": "Ивент",
        },
    )
    assert res_news.status_code in (200, 201)


@pytest.mark.asyncio
async def test_user_journey_admin_analytics_audit(journey_env):
    """User Journey 6: Admin inspecting real user activity generated during sessions."""
    client, repo = journey_env

    # 1. Simulate user actions: search & server visit
    unique_tag = f"audit_{uuid.uuid4().hex[:6]}"
    await client.get(f"/search?q={unique_tag}")
    await client.get(f"/server/donutsmp.net?mock=true")
    await client.post(
        "/api/analytics/event",
        json={"event_type": "copy_ip", "target": "donutsmp.net", "metadata": {"tag": unique_tag}},
    )

    # 2. Register / login as admin
    admin_uname = f"admin_{uuid.uuid4().hex[:8]}"
    admin_id = await repo.create_user(
        username=admin_uname,
        password_hash=hash_password("adminSecret123"),
        role="admin",
    )
    admin_token = await repo.create_session(f"token_{uuid.uuid4().hex[:8]}", admin_id)
    client.cookies.set("session_token", admin_token)

    # 3. Access analytics dashboard
    res_dash = await client.get("/analytics?hours=24")
    assert res_dash.status_code == 200
    assert "Телеметрия и активность сайта" in res_dash.text
    assert "Что вбивают пользователи" in res_dash.text
    assert "Что смотрят (Популярные серверы)" in res_dash.text
    assert "Живой поток действий" in res_dash.text
    assert unique_tag in res_dash.text
