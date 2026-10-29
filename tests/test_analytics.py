"""Tests for site telemetry, visitor tracking, search query logging, and admin analytics dashboard."""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.repository import ServerRepository
from app.services.auth_service import hash_password


@pytest_asyncio.fixture
async def test_env():
    """Initialize DB and repository with clean state."""
    await init_db()
    repo = ServerRepository()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, repo


@pytest.mark.asyncio
async def test_repository_analytics_methods(test_env):
    """Verify repository methods record and aggregate analytics correctly."""
    _, repo = test_env

    # 1. Record Pageviews
    await repo.record_pageview(
        visitor_id="visitor-abc",
        path="/server/mc.hypixel.net",
        server_address="mc.hypixel.net",
        page_title="Hypixel Network",
        device_type="desktop",
        browser="Chrome",
        ip_hash="hash123",
    )
    await repo.record_pageview(
        visitor_id="visitor-xyz",
        path="/server/mc.hypixel.net",
        server_address="mc.hypixel.net",
        page_title="Hypixel Network",
        device_type="mobile",
        browser="Safari",
        ip_hash="hash456",
    )
    await repo.record_pageview(
        visitor_id="visitor-abc",
        path="/server/2b2t.org",
        server_address="2b2t.org",
        page_title="2b2t",
        device_type="desktop",
        browser="Chrome",
        ip_hash="hash123",
    )

    # 2. Record Searches
    await repo.record_search(
        visitor_id="visitor-abc",
        query="hypixel",
        edition="java",
        results_count=1,
        matched_server="mc.hypixel.net",
    )
    await repo.record_search(
        visitor_id="visitor-xyz",
        query="hypixel",
        edition="java",
        results_count=1,
        matched_server="mc.hypixel.net",
    )
    await repo.record_search(
        visitor_id="visitor-abc",
        query="anarchy",
        edition="java",
        results_count=2,
        matched_server="2b2t.org",
    )

    # 3. Record Interactive Events
    await repo.record_event(
        visitor_id="visitor-abc",
        event_type="copy_ip",
        target="mc.hypixel.net",
        metadata="home_catalog",
    )
    await repo.record_event(
        visitor_id="visitor-xyz",
        event_type="launch_client",
        target="mc.hypixel.net",
        metadata="server_page",
    )

    # Verify Summary
    summary = await repo.get_analytics_summary(hours=24)
    assert summary["total_pageviews"] >= 3
    assert summary["unique_visitors"] >= 2
    assert summary["total_searches"] >= 3
    assert summary["total_conversions"] >= 2

    # Verify Top Searches
    top_searches = await repo.get_top_searches(limit=10, hours=24)
    assert len(top_searches) >= 2
    assert top_searches[0]["query"] == "hypixel"
    assert top_searches[0]["count"] >= 2

    # Verify Top Viewed Servers
    top_servers = await repo.get_top_viewed_servers(limit=10, hours=24)
    assert len(top_servers) >= 2
    assert top_servers[0]["server_address"] == "mc.hypixel.net"
    assert top_servers[0]["view_count"] >= 2

    # Verify Recent Activity Stream
    activity = await repo.get_recent_activity_stream(limit=10)
    assert len(activity) >= 3


@pytest.mark.asyncio
async def test_client_event_beacon_endpoint(test_env):
    """Verify POST /api/analytics/event records client interactions."""
    client, repo = test_env
    res = await client.post(
        "/api/analytics/event",
        json={
            "event_type": "copy_ip",
            "target": "mc.hypixel.net",
            "metadata": "quick_copy",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_search_and_pageview_automatic_recording(test_env):
    """Verify search queries and pageviews are recorded automatically upon request."""
    client, repo = test_env
    # Perform search request
    res = await client.get("/search?q=testpvpquery")
    assert res.status_code == 200

    # Ensure cookie vv_vid was set
    assert "vv_vid" in res.cookies

    # Verify search was logged in repo
    top_searches = await repo.get_top_searches(limit=50, hours=24)
    assert any(s["query"] == "testpvpquery" for s in top_searches)


@pytest.mark.asyncio
async def test_analytics_dashboard_access_control(test_env):
    """Verify /analytics requires admin privileges."""
    client, repo = test_env

    # 1. Unauthenticated request -> redirects or 403
    res_unauth = await client.get("/analytics", follow_redirects=False)
    assert res_unauth.status_code in (302, 303, 307, 403)

    # 2. Regular user account -> 403 Forbidden
    reg_name = f"reguser_{uuid.uuid4().hex[:8]}"
    reg_user_id = await repo.create_user(
        username=reg_name,
        password_hash=hash_password("pass123"),
        role="user",
    )
    token_reg = await repo.create_session(f"session_reg_{uuid.uuid4().hex[:8]}", reg_user_id)
    client.cookies.set("session_token", token_reg)
    res_user = await client.get("/analytics", follow_redirects=False)
    assert res_user.status_code in (403, 303)

    # 3. Admin user account -> 200 OK with analytics dashboard
    admin_name = f"admin_{uuid.uuid4().hex[:8]}"
    admin_user_id = await repo.create_user(
        username=admin_name,
        password_hash=hash_password("adminpass"),
        role="admin",
    )
    token_admin = await repo.create_session(f"session_admin_{uuid.uuid4().hex[:8]}", admin_user_id)
    client.cookies.set("session_token", token_admin)
    res_admin = await client.get("/analytics")
    assert res_admin.status_code == 200
    assert "Аналитика" in res_admin.text or "Статистика" in res_admin.text
    assert "mc.hypixel.net" in res_admin.text or "Просмотры" in res_admin.text
