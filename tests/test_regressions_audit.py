"""TDD regression tests reproducing bugs left by previous model iterations."""

import json
import re
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Headers

from app.config import settings
from app.database import init_db
from app.limiter import get_real_client_ip
from app.main import app
from app.repository import ServerRepository
from app.services.probes_service import get_multi_region_probes


@pytest_asyncio.fixture
async def client():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac, ServerRepository()


@pytest.mark.asyncio
async def test_invalid_scanner_and_ssrf_addresses_no_500_or_db_persist(client):
    """Scanner paths (.env, s3.js) and SSRF targets must never 500 or pollute servers table."""
    ac, repo = client

    res_page = await ac.get("/server/.env")
    assert res_page.status_code != 500
    res_card = await ac.get("/partials/server-card?address=.env")
    assert res_card.status_code != 500
    res_ping = await ac.post("/api/ping/.env")
    assert res_ping.status_code != 500

    assert await repo.get_or_create_server("s3.js") == 0
    assert await repo.get_or_create_server("127.0.0.1:25565") == 0

    await ac.get("/api/status/127.0.0.1:25565")
    servers = await repo.get_all_servers()
    addrs = {s["address"] for s in servers}
    assert "127.0.0.1:25565" not in addrs
    assert "s3.js" not in addrs


@pytest.mark.asyncio
async def test_mock_param_ignored_when_mock_auth_disabled(client):
    """When enable_mock_auth is False (prod), ?mock=true must not return fake 1420 players or write to DB."""
    ac, repo = client
    orig = settings.enable_mock_auth
    try:
        settings.enable_mock_auth = False
        res = await ac.get("/api/status/nonexistent-test-999.invalid?mock=true")
        assert res.status_code == 200
        assert res.json()["players_online"] != 1420

        res_badge = await ac.get("/api/badge/nonexistent-test-999.invalid.svg?mock=true")
        assert res_badge.status_code == 200
        assert "1,420" not in res_badge.text
    finally:
        settings.enable_mock_auth = orig


@pytest.mark.asyncio
async def test_server_html_markup_navbar_docs_and_legal_pages(client):
    """Verify server HTML has no dangling closing tags, navbar hides disabled /docs, and legal pages support light theme."""
    ac, repo = client
    res_srv = await ac.get("/server/mc.hypixel.net?mock=true")
    assert res_srv.status_code == 200
    assert not re.search(r"</span>\s*\d+\s*Players\s*</span>", res_srv.text)

    orig_docs = settings.enable_docs
    try:
        settings.enable_docs = False
        res_home = await ac.get("/")
        assert 'href="/docs"' not in res_home.text
    finally:
        settings.enable_docs = orig_docs

    res_priv = await ac.get("/privacy")
    assert res_priv.status_code == 200
    assert '<h1 class="text-2xl font-bold text-white' not in res_priv.text
    res_terms = await ac.get("/terms")
    assert res_terms.status_code == 200
    assert '<h1 class="text-2xl font-bold text-white' not in res_terms.text


@pytest.mark.asyncio
async def test_i18n_referer_localization_suggestions_cards_and_probes(client):
    """Language switch must preserve same-origin referer while blocking external hosts; EN UI & API must be localized."""
    ac, _ = client

    # Same-origin referer preserved
    res_same = await ac.get(
        "/set-lang/en",
        headers={"Referer": "http://testserver/server/mc.hypixel.net?bedrock=false"},
        follow_redirects=False,
    )
    assert res_same.status_code == 303
    assert res_same.headers["location"] == "/server/mc.hypixel.net?bedrock=false"

    # External referer blocked
    res_evil = await ac.get(
        "/set-lang/en",
        headers={"Referer": "https://evil.com/phishing"},
        follow_redirects=False,
    )
    assert res_evil.status_code == 303
    assert res_evil.headers["location"] == "/"

    # Search page & Suggestions localized in English
    res_search_en = await ac.get("/search?q=craft", headers={"Cookie": "vv_lang=en"})
    assert res_search_en.status_code == 200
    assert "Мини-игры" not in res_search_en.text
    assert "Популярная сеть мини-игр" not in res_search_en.text

    res_sug_en = await ac.get("/api/suggestions?q=craft", headers={"Cookie": "vv_lang=en"})
    assert res_sug_en.status_code == 200
    assert all("Мини-игры" not in s["category_label"] for s in res_sug_en.json())
    assert all("Опросить узел" not in s["description"] for s in res_sug_en.json())

    # Server card partial localized in English (no hardcoded Russian status badges)
    res_card_en = await ac.get("/partials/server-card?address=mc.hypixel.net&mock=true", headers={"Cookie": "vv_lang=en"})
    assert res_card_en.status_code == 200
    for ru_word in ("Отличный", "Хороший", "Высокий", "Низкий пинг", "Высокий онлайн", "Пик:"):
        assert ru_word not in res_card_en.text

    # Probes localized in English
    probes_en = get_multi_region_probes("mc.hypixel.net", 25.0, lang="en")
    assert probes_en[0]["city"] == "Moscow"
    assert probes_en[0]["country"] == "Russia"


def test_trusted_proxy_xff_rightmost_client_ip():
    """Behind trusted proxy, rightmost client IP before proxy must be used rather than spoofed leftmost XFF."""
    class DummyClient:
        host = "127.0.0.1"

    class DummyReq:
        client = DummyClient()
        headers = Headers({"X-Forwarded-For": "8.8.8.8, 198.51.100.42"})

    assert get_real_client_ip(DummyReq()) == "198.51.100.42"
