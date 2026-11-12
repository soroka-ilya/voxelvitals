"""Comprehensive security regression and verification tests for VoxelVitals."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.config import settings
from app.database import init_db
from app.main import app
from app.repository import ServerRepository
from app.services.alias_service import resolve_address
from app.services.auth_service import hash_password, verify_password
from app.services.pinger import is_safe_address, query_server

import pytest_asyncio

repo = ServerRepository()


@pytest_asyncio.fixture
async def client():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_oauth_mock_disabled_by_default(client):
    """Vulnerability 1: Ensure OAuth mock is rejected when enable_mock_auth is False."""
    orig = settings.enable_mock_auth
    try:
        settings.enable_mock_auth = False
        res = await client.get("/api/auth/google/login?mock=true")
        assert res.status_code in (403, 400), "Mock login must be rejected when disabled"
        res_cb = await client.get("/api/auth/google/callback?mock=true")
        assert res_cb.status_code in (403, 400), "Mock callback must be rejected when disabled"
    finally:
        settings.enable_mock_auth = orig


def test_reflected_xss_address_sanitization():
    """Vulnerability 2: resolve_address must reject/strip dangerous script characters."""
    dangerous = "hypixel.net');alert(1);//"
    resolved = resolve_address(dangerous)
    for bad_char in ("'", '"', "(", ")", ";", "<", ">"):
        assert bad_char not in resolved, f"Dangerous character {bad_char} found in resolved address"


@pytest.mark.asyncio
async def test_news_publication_requires_admin(client):
    """Vulnerability 3: POST /api/news must reject unauthenticated/non-admin users."""
    orig = settings.require_news_admin
    try:
        settings.require_news_admin = True
        # Unauthenticated request
        res = await client.post(
            "/api/news",
            json={
                "server_address": "mc.hypixel.net",
                "title": "Hacked Title",
                "content": "Malicious announcement",
                "tag": "Обновление",
            },
        )
        assert res.status_code in (401, 403), "Unauthenticated news creation must be forbidden"
    finally:
        settings.require_news_admin = orig


@pytest.mark.asyncio
async def test_ssrf_and_private_ip_blocking():
    """Vulnerability 4: Internal/private/loopback addresses must be blocked from pinging."""
    assert not is_safe_address("127.0.0.1"), "Loopback IPv4 must not be safe"
    assert not is_safe_address("localhost"), "Localhost must not be safe"
    assert not is_safe_address("169.254.169.254"), "AWS/Cloud metadata IP must not be safe"
    assert not is_safe_address("10.0.0.1"), "Private 10/8 IP must not be safe"
    assert not is_safe_address("192.168.1.1"), "Private 192.168/16 IP must not be safe"
    assert is_safe_address("mc.hypixel.net"), "Public domain must be safe"

    status = await query_server("127.0.0.1:25565")
    assert not status.is_online
    assert "127.0.0.1" not in (status.error_message or "") or "запрещен" in (status.error_message or "").lower() or "blocked" in (status.error_message or "").lower()


@pytest.mark.asyncio
async def test_open_redirect_protection(client):
    """Vulnerability 5: Language switcher must not permit open redirects to protocol-relative or external URLs."""
    # Protocol-relative redirect attempt
    res = await client.get("/set-lang/en?redirect=//evil.com", follow_redirects=False)
    assert res.status_code == 303
    location = res.headers["location"]
    assert not location.startswith("//"), f"Protocol-relative redirect allowed: {location}"
    assert not location.startswith("http://") and not location.startswith("https://")

    # Backslash redirect attempt
    res_bs = await client.get(r"/set-lang/en?redirect=/\evil.com", follow_redirects=False)
    assert res_bs.status_code == 303
    assert not res_bs.headers["location"].startswith("/\\")


def test_password_hashing_scrypt_and_legacy_compatibility():
    """Vulnerability 8: Passwords must use scrypt, while preserving legacy sha256 verification."""
    pwd = "SuperSecretPassword123!"
    new_hash = hash_password(pwd)
    assert new_hash.startswith("scrypt$"), f"New password hash should use scrypt: {new_hash}"
    assert verify_password(pwd, new_hash), "Scrypt hash verification failed"
    assert not verify_password("WrongPassword", new_hash), "Wrong password verified successfully"

    # Legacy SHA-256 hash test
    legacy_salt = "abcdef0123456789"
    import hashlib
    legacy_key = hashlib.sha256((legacy_salt + pwd).encode("utf-8")).hexdigest()
    legacy_hash = f"{legacy_salt}${legacy_key}"
    assert verify_password(pwd, legacy_hash), "Legacy sha256 verification failed"


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Vulnerability 11: Security headers must be set on responses."""
    res = await client.get("/")
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert "referrer-policy" in res.headers
    assert "strict-transport-security" in res.headers


@pytest.mark.asyncio
async def test_logout_post_method(client):
    """Vulnerability 12: POST /api/auth/logout clears user session."""
    # Register a temp user
    u_name = "logout_test_user"
    reg_res = await client.post("/api/auth/register", json={"username": u_name, "password": "Password123!"})
    assert reg_res.status_code == 201
    session_token = reg_res.cookies.get("session_token")
    assert session_token

    # Perform POST logout
    logout_res = await client.post("/api/auth/logout", cookies={"session_token": session_token})
    assert logout_res.status_code == 200

    # Verify session is invalidated
    me_res = await client.get("/api/auth/me", cookies={"session_token": session_token})
    assert me_res.status_code == 401


@pytest.mark.asyncio
async def test_health_check_information_leakage(client):
    """Vulnerability 14: /api/health must not disclose raw DB exceptions."""
    res = await client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "traceback" not in str(data).lower()


@pytest.mark.asyncio
async def test_rate_limiter_spoofed_headers_ignored(client):
    """Vulnerability 6: X-Forwarded-For must be ignored if request is not from trusted proxy."""
    from app.limiter import get_real_client_ip
    from starlette.datastructures import Headers

    class DummyClient:
        host = "203.0.113.195"  # Untrusted external IP

    class DummyRequest:
        client = DummyClient()
        headers = Headers({"X-Forwarded-For": "1.1.1.1", "X-Real-IP": "1.1.1.1"})

    req = DummyRequest()
    ip = get_real_client_ip(req)
    assert ip == "203.0.113.195", f"Rate limiter trusted spoofed header from untrusted peer: {ip}"


def test_sliding_window_limiter_cleanup_memory():
    """Vulnerability 6: SlidingWindowRateLimiter must prune expired records to prevent memory leak."""
    from app.services.rate_limiter import SlidingWindowRateLimiter
    limiter_inst = SlidingWindowRateLimiter(requests_limit=5, window_seconds=1)
    limiter_inst._records["old_key:path"] = [1.0, 2.0]
    limiter_inst._cleanup_expired(now=100.0)
    assert "old_key:path" not in limiter_inst._records, "Expired key was not purged from memory"


@pytest.mark.asyncio
async def test_telegram_webhook_secret_enforcement(client):
    """Vulnerability 7: Telegram webhook must enforce secret token header when configured."""
    settings.telegram_webhook_secret = "secret_verification_token_123"
    try:
        # Without secret token
        res_no_sec = await client.post("/api/tg/webhook", json={"update_id": 1})
        assert res_no_sec.status_code == 403

        # With wrong token
        res_bad_sec = await client.post(
            "/api/tg/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"},
        )
        assert res_bad_sec.status_code == 403

        # With valid token
        res_valid = await client.post(
            "/api/tg/webhook",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": "secret_verification_token_123"},
        )
        assert res_valid.status_code == 200
    finally:
        settings.telegram_webhook_secret = ""


@pytest.mark.asyncio
async def test_secure_cookie_under_https(client):
    """Vulnerability 9: Cookies must include Secure flag when running under HTTPS."""
    settings.enable_mock_auth = True
    res = await client.get("/api/auth/google/login?mock=true", headers={"x-forwarded-proto": "https"})
    assert res.status_code == 302
    set_cookie_header = res.headers.get("set-cookie", "")
    assert "secure" in set_cookie_header.lower(), "Cookie missing Secure flag on HTTPS connection"


@pytest.mark.asyncio
async def test_oauth_unverified_email_linking_prevented():
    """Vulnerability 10: OAuth must not link by unverified email."""
    # Create existing local user with target email
    target_email = "victim@example.com"
    pwd_h = hash_password("Password123!")
    user_id = await repo.create_user(
        username="victim_account",
        password_hash=pwd_h,
        email=target_email,
    )
    assert user_id > 0

    # Attempt to link unverified OAuth identity with same email
    oauth_user = await repo.create_or_link_oauth_user(
        provider="google",
        provider_id="attacker_google_id_999",
        email=target_email,
        email_verified=False,
    )
    assert oauth_user["id"] != user_id, "Account takeover occurred: unverified email linked to victim account!"


def test_icon_base64_validation():
    """Vulnerability 15: Invalid/malicious icon_base64 values must be sanitized to None."""
    from app.domain.models import ServerStatus
    status_bad = ServerStatus(
        address="mc.test.net",
        is_online=True,
        icon_base64="javascript:alert('xss')",
    )
    assert status_bad.icon_base64 is None, "Malicious javascript URI in icon_base64 was not sanitized"

    status_good = ServerStatus(
        address="mc.test.net",
        is_online=True,
        icon_base64="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY44YAAAAASUVORK5CYII=",
    )
    assert status_good.icon_base64 is not None, "Valid png base64 was unexpectedly removed"
