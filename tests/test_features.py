"""Tests for new features: auth, reviews, news, contacts, launcher connect, and theme."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.repository import ServerRepository


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_auth_workflow(client):
    """Test user registration, login, session check, and logout."""
    import uuid
    uname = f"user_{uuid.uuid4().hex[:8]}"
    # 1. Register a new user
    reg_res = await client.post(
        "/api/auth/register",
        json={
            "username": uname,
            "password": "securepassword123",
            "mc_nickname": "StevePro",
            "email": f"{uname}@example.com",
        },
    )
    assert reg_res.status_code in (200, 201)
    data = reg_res.json()
    assert data["username"] == uname
    assert data["mc_nickname"] == "StevePro"

    # 2. Login
    login_res = await client.post(
        "/api/auth/login",
        json={"username": uname, "password": "securepassword123"},
    )
    assert login_res.status_code == 200
    assert "session_token" in login_res.cookies
    client.cookies.update(login_res.cookies)

    # 3. Check me endpoint
    me_res = await client.get("/api/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["username"] == uname

    # 4. Logout
    logout_res = await client.get("/api/auth/logout")
    assert logout_res.status_code == 200



@pytest.mark.asyncio
async def test_server_reviews_and_news(client):
    """Test submitting and fetching reviews and news for a server."""
    import uuid
    r_uname = f"rev_{uuid.uuid4().hex[:8]}"
    # Register & Login
    await client.post(
        "/api/auth/register",
        json={"username": r_uname, "password": "pass123456", "mc_nickname": "Alex"},
    )
    login_res = await client.post(
        "/api/auth/login",
        json={"username": r_uname, "password": "pass123456"},
    )
    client.cookies.update(login_res.cookies)

    # Post a review
    rev_res = await client.post(
        "/api/reviews",
        json={
            "server_address": "mc.hypixel.net",
            "rating": 5,
            "comment": "Отличный сервер, играем с друзьями каждый день!",
        },
    )
    assert rev_res.status_code == 200
    rev_data = rev_res.json()
    assert rev_data["rating"] == 5

    # Get reviews for server
    list_res = await client.get("/api/reviews?address=mc.hypixel.net")
    assert list_res.status_code == 200
    reviews = list_res.json()
    assert len(reviews) >= 1
    assert any(r["comment"] == "Отличный сервер, играем с друзьями каждый день!" for r in reviews)

    # Post a news article
    news_res = await client.post(
        "/api/news",
        json={
            "server_address": "mc.hypixel.net",
            "title": "Большое летнее обновление мини-игр",
            "content": "Добавлены новые карты для BedWars и SkyWars!",
            "tag": "Обновление",
        },
    )

    assert news_res.status_code == 200

    # Get news for server
    news_list_res = await client.get("/api/news?address=mc.hypixel.net")
    assert news_list_res.status_code == 200
    news = news_list_res.json()
    assert len(news) >= 1
    assert any(n["title"] == "Большое летнее обновление мини-игр" for n in news)


@pytest.mark.asyncio
async def test_server_page_new_elements_and_removed_elements(client):
    """Verify server detail page has launcher button, contacts, news, reviews, screenshots, and removed raw svg/markdown."""
    res = await client.get("/server/mc.hypixel.net?mock=true")
    assert res.status_code == 200
    html = res.text

    # Raw SVG and Markdown Snippet must be removed
    assert "Open Raw SVG" not in html
    assert "Markdown Snippet" not in html

    # Launcher quick connect button
    assert "лаунчер" in html.lower() or "launcher" in html.lower()

    # Contacts (Discord, VK, etc.)
    assert "discord" in html.lower() or "vk" in html.lower()

    # News section
    assert "новост" in html.lower() or "news" in html.lower()

    # Reviews section
    assert "отзыв" in html.lower() or "review" in html.lower()

    # Screenshots section
    assert "скриншот" in html.lower() or "screenshot" in html.lower()


@pytest.mark.asyncio
async def test_light_theme_and_cursor_card_classes(client):
    """Verify base template has auto theme switch script and cards have cursor-pointer."""
    # Check index page
    res_home = await client.get("/")
    assert res_home.status_code == 200
    assert "prefers-color-scheme" in res_home.text
    assert "cursor-pointer" in res_home.text

    # Check server card partial
    res_card = await client.get("/partials/server-card?address=mc.hypixel.net&mock=true")
    assert res_card.status_code == 200
    assert "cursor-pointer" in res_card.text


@pytest.mark.asyncio
async def test_vote_and_auth_edge_cases(client):
    """Test vote deduplication, invalid credentials, and unauthorized access."""
    import uuid
    v_addr = f"vote-{uuid.uuid4().hex[:8]}.net"
    # 1. Vote once
    v1 = await client.post("/api/vote", json={"server_address": v_addr})
    assert v1.status_code == 200
    assert v1.json()["success"] is True

    # 2. Vote twice from same IP
    v2 = await client.post("/api/vote", json={"server_address": v_addr})
    assert v2.status_code == 200
    assert v2.json()["success"] is False
    assert "уже голосовали" in v2.json()["message"]

    # 3. Invalid login credentials
    bad_login = await client.post(
        "/api/auth/login",
        json={"username": "nonexistent_user_999", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 4. Access /api/auth/me without auth cookie
    unauth = await client.get("/api/auth/me")
    assert unauth.status_code == 401


@pytest.mark.asyncio
async def test_server_card_online_vs_offline_telemetry(client):
    """Verify that offline server cards display diagnostic info and NOT fake TPS 20.0 or 99.9% uptime."""
    from unittest.mock import patch
    from app.domain.models import ServerStatus

    offline_status = ServerStatus(
        address="offline.server.test",
        is_online=False,
        error_message="Connection timed out after 3.0 seconds",
        latency_ms=0.0,
    )
    with patch("app.api.routes.query_server", return_value=offline_status):
        res = await client.get("/partials/server-card?address=offline.server.test")
        assert res.status_code == 200
        text = res.text
        # Must not display fake TPS 20.0 or 99.9% uptime when offline!
        assert "Стабильный TPS 20.0" not in text
        assert "99.9%" not in text
        # Must display offline diagnostics
        assert "Offline" in text or "Недоступен" in text


@pytest.mark.asyncio
async def test_light_theme_tokens_contrast(client):
    """Verify section titles on index and server pages have dark/light contrast classes."""
    res_home = await client.get("/")
    assert res_home.status_code == 200
    home_html = res_home.text
    # Section titles must be visible in light theme (not bare text-white)
    assert '<h2 class="text-xl font-bold text-white' not in home_html
    assert '<h2 class="text-lg font-semibold text-white' not in home_html

    # Check server page
    res_server = await client.get("/server/mc.hypixel.net?mock=true")
    assert res_server.status_code == 200
    server_html = res_server.text
    assert '<h2 class="text-base font-semibold text-white">24-Hour Telemetry' not in server_html
    assert '<h2 class="text-base font-semibold text-white">Online Player' not in server_html


@pytest.mark.asyncio
async def test_audit_enhancements(client):
    """Verify improvements from audit: data-tags, rating stats sync, badge preview, responsive header."""
    # 1. Index page catalog cards have data-tags
    res_home = await client.get("/")
    assert res_home.status_code == 200
    assert "data-tags=" in res_home.text

    # 2. Server page header responsive break classes and rating sync
    res_server = await client.get("/server/donutsmp.net?mock=true")
    assert res_server.status_code == 200
    html = res_server.text

    # Header break-all sm:break-normal
    assert "break-all sm:break-normal" in html

    # Demo rating stats synchronized with demo reviews count (3 reviews, not 0)
    assert "(3 отзывов)" in html
    assert "(0 отзывов)" not in html

    # Live status badge preview card present, without forbidden strings
    assert "/api/badge/donutsmp.net.svg" in html
    assert "Open Raw SVG" not in html
    assert "Markdown Snippet" not in html

    # 3. Server card partial responsive toolbar
    res_card = await client.get("/partials/server-card?address=mc.hypixel.net&mock=true")
    assert res_card.status_code == 200
    assert "flex-wrap gap-y-2" in res_card.text

    # 4. Catalog cards contain survival tag for DonutSMP, 2b2t, ReallyWorld
    assert 'data-tags="anarchy,survival,smp,hardcore,donutsmp,donut"' in res_home.text
    assert 'data-tags="anarchy,survival,2b2t,2b,vanilla"' in res_home.text
    assert 'data-tags="anarchy,survival,reallyworld,rw,really"' in res_home.text

    # 5. Badge code copy uses safe copySnippet helper
    assert "copySnippet(" in html

