"""Tests for Google and Microsoft (Xbox / Minecraft) OAuth 2.0 authentication."""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import get_db_connection, init_db
from app.main import app
from app.repository import ServerRepository


@pytest_asyncio.fixture
async def oauth_env():
    """Setup clean database and async test client."""
    await init_db()
    repo = ServerRepository()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, repo


@pytest.mark.asyncio
async def test_oauth_migration_columns(oauth_env):
    """Verify that user table contains google_id, microsoft_id, avatar_url, and is_verified_license."""
    client, repo = oauth_env
    async with get_db_connection(repo.db_path) as conn:
        cursor = await conn.execute("PRAGMA table_info(users)")
        cols = {row["name"] for row in await cursor.fetchall()}
        assert "google_id" in cols
        assert "microsoft_id" in cols
        assert "avatar_url" in cols
        assert "is_verified_license" in cols


@pytest.mark.asyncio
async def test_repository_oauth_create_and_link(oauth_env):
    """Verify repository can create OAuth users and link accounts by email."""
    client, repo = oauth_env
    unique_email = f"gamer_{uuid.uuid4().hex[:8]}@example.com"
    google_id = f"gid_{uuid.uuid4().hex[:10]}"
    ms_id = f"msid_{uuid.uuid4().hex[:10]}"

    # 1. First user logs in with Google
    user_google = await repo.create_or_link_oauth_user(
        provider="google",
        provider_id=google_id,
        email=unique_email,
        name="Alex Google",
        avatar_url="https://lh3.googleusercontent.com/avatar1",
    )
    assert user_google["google_id"] == google_id
    assert user_google["email"] == unique_email
    assert user_google["is_verified_license"] == 0

    # 2. Same user later logs in with Microsoft with same email & verified Minecraft license
    user_linked = await repo.create_or_link_oauth_user(
        provider="microsoft",
        provider_id=ms_id,
        email=unique_email,
        name="Alex Xbox",
        mc_nickname="AlexMinecraft",
        is_verified_license=True,
    )
    # Must link to same account ID
    assert user_linked["id"] == user_google["id"]
    assert user_linked["google_id"] == google_id
    assert user_linked["microsoft_id"] == ms_id
    assert user_linked["mc_nickname"] == "AlexMinecraft"
    assert user_linked["is_verified_license"] == 1


@pytest.mark.asyncio
async def test_google_oauth_flow(oauth_env):
    """Verify Google login redirects and callback issues session token."""
    client, repo = oauth_env

    # 1. Login initiation
    res_login = await client.get("/api/auth/google/login?mock=true", follow_redirects=False)
    assert res_login.status_code == 302
    assert "oauth_state_google" in res_login.cookies
    assert "/api/auth/google/callback" in res_login.headers["location"]

    # 2. Callback handling
    client.cookies.set("oauth_state_google", "test_mock_state")
    res_cb = await client.get(
        "/api/auth/google/callback?code=mock_code&state=test_mock_state&mock=true",
        follow_redirects=False,
    )
    assert res_cb.status_code == 303
    assert "session_token" in res_cb.cookies
    session_token = res_cb.cookies["session_token"]

    # 3. Verify user profile can be fetched with session token
    client.cookies.set("session_token", session_token)
    res_me = await client.get("/api/auth/me")
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["role"] == "user"
    assert "Google Gamer" in me_data["username"] or "google" in me_data["username"].lower()


@pytest.mark.asyncio
async def test_microsoft_oauth_minecraft_verification(oauth_env):
    """Verify Microsoft login returns verified Minecraft license and nickname."""
    client, repo = oauth_env

    # 1. Login initiation
    res_login = await client.get("/api/auth/microsoft/login?mock=true", follow_redirects=False)
    assert res_login.status_code == 302
    assert "oauth_state_microsoft" in res_login.cookies

    # 2. Callback handling with mock Minecraft profile
    client.cookies.set("oauth_state_microsoft", "ms_state_val")
    res_cb = await client.get(
        "/api/auth/microsoft/callback?code=mock_ms_code&state=ms_state_val&mock=true",
        follow_redirects=False,
    )
    assert res_cb.status_code == 303
    assert "session_token" in res_cb.cookies
    session_token = res_cb.cookies["session_token"]

    # 3. Check current user profile has verified license
    client.cookies.set("session_token", session_token)
    res_me = await client.get("/api/auth/me")
    assert res_me.status_code == 200
    user_data = res_me.json()
    assert user_data["mc_nickname"] == "Steve"


@pytest.mark.asyncio
async def test_unconfigured_oauth_redirects_with_notice(oauth_env):
    """Verify attempting to login without configured keys redirects with notice for developer."""
    client, repo = oauth_env
    # Without mock=true and without real keys in env -> friendly redirect with notice
    res_google = await client.get("/api/auth/google/login", follow_redirects=False)
    assert res_google.status_code in (302, 303, 307)
    assert "auth_notice=google_setup" in res_google.headers["location"]

    res_ms = await client.get("/api/auth/microsoft/login", follow_redirects=False)
    assert res_ms.status_code in (302, 303, 307)
    assert "auth_notice=microsoft_setup" in res_ms.headers["location"]


@pytest.mark.asyncio
async def test_oauth_csrf_state_validation(oauth_env):
    """Verify CSRF state mismatch is rejected with 400 Bad Request."""
    client, repo = oauth_env
    client.cookies.set("oauth_state_google", "valid_cookie_state")
    res_tampered = await client.get("/api/auth/google/callback?code=abc&state=evil_hacker_state")
    assert res_tampered.status_code == 400
    assert "CSRF state" in res_tampered.json()["detail"]
