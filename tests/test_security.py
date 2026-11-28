"""Comprehensive security regression and verification tests for VoxelVitals."""

import pytest
from httpx import AsyncClient, ASGITransport
from app.config import settings
from app.database import init_db
from app.main import app
from app.repository import ServerRepository
from app.services.alias_service import resolve_address
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
async def test_rkn_personal_data_and_ori_endpoints_removed(client):
    """Verify user auth, OAuth, UGC comments/news/votes, and visitor tracking endpoints return 404."""
    for method, path in [
        ("GET", "/api/auth/google/login"),
        ("GET", "/api/auth/microsoft/login"),
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/me"),
        ("POST", "/api/reviews"),
        ("POST", "/api/news"),
        ("POST", "/api/vote"),
        ("POST", "/api/analytics/event"),
        ("GET", "/analytics"),
    ]:
        res = await client.request(method, path)
        assert res.status_code == 404, f"{method} {path} unexpectedly active: {res.status_code}"


@pytest.mark.asyncio
async def test_no_tracking_cookies_or_external_cdns(client):
    """Verify responses set no tracking cookies (vv_vid) and embed no Google Fonts or external CDN images."""
    res_home = await client.get("/")
    assert res_home.status_code == 200
    assert "vv_vid" not in res_home.cookies
    assert "vv_vid" not in res_home.headers.get("set-cookie", "")
    assert "fonts.googleapis.com" not in res_home.text
    assert "fonts.gstatic.com" not in res_home.text
    assert "mc-heads.net" not in res_home.text
    assert "/static/css/fonts.css" in res_home.text

    res_srv = await client.get("/server/mc.hypixel.net?mock=true")
    assert res_srv.status_code == 200
    assert "fonts.googleapis.com" not in res_srv.text
    assert "mc-heads.net" not in res_srv.text


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


@pytest.mark.asyncio
async def test_security_headers_present(client):
    """Vulnerability 11: Security headers must be set on responses."""
    res = await client.get("/")
    assert res.headers.get("x-frame-options") == "DENY"
    assert res.headers.get("x-content-type-options") == "nosniff"
    assert "referrer-policy" in res.headers
    assert "strict-transport-security" in res.headers


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
