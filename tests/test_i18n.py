"""Comprehensive test suite for VoxelVitals multi-language (i18n) system."""

import json
from pathlib import Path
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.database import init_db
from app.main import app
from app.services.i18n_service import (
    DEFAULT_LANGUAGE,
    LANGUAGE_METADATA,
    LOCALES_DIR,
    SUPPORTED_LANGUAGES,
    get_request_language,
    parse_accept_language,
    set_current_lang,
    t,
)


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def test_supported_languages_and_metadata():
    """Verify all 4 core languages are supported with complete metadata."""
    assert SUPPORTED_LANGUAGES == ("ru", "en", "zh", "de")
    assert DEFAULT_LANGUAGE == "ru"
    for code in SUPPORTED_LANGUAGES:
        assert code in LANGUAGE_METADATA
        meta = LANGUAGE_METADATA[code]
        assert meta["code"] == code
        assert "name" in meta
        assert "flag" in meta
        assert "locale" in meta


def test_locales_files_exist_and_valid_json():
    """Verify all locale JSON files exist, are valid JSON, and share top-level structure."""
    expected_top_keys = {
        "meta",
        "nav",
        "hero",
        "catalog",
        "categories",
        "server_card",
        "server_detail",
        "quick_connect",
        "search",
        "auth",
        "news_modal",
        "footer",
        "probes",
    }
    for code in SUPPORTED_LANGUAGES:
        file_path = LOCALES_DIR / f"{code}.json"
        assert file_path.exists(), f"Locale file missing: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict)
            assert data["meta"]["code"] == code
            assert expected_top_keys.issubset(set(data.keys())), (
                f"Missing keys in {code}.json: {expected_top_keys - set(data.keys())}"
            )


def test_parse_accept_language():
    """Test RFC 9110 Accept-Language parsing with quality values and regions."""
    # Standard single tag
    assert parse_accept_language("en") == "en"
    assert parse_accept_language("ru") == "ru"
    assert parse_accept_language("zh") == "zh"
    assert parse_accept_language("de") == "de"

    # Region tags
    assert parse_accept_language("en-US,en;q=0.9") == "en"
    assert parse_accept_language("zh-CN,zh;q=0.8") == "zh"
    assert parse_accept_language("de-DE,de;q=0.9,en;q=0.8") == "de"
    assert parse_accept_language("ru-RU,ru;q=0.9") == "ru"

    # Quality factor sorting
    assert parse_accept_language("fr;q=0.9, de;q=0.8, en;q=0.5") == "de"
    assert parse_accept_language("es;q=0.9, zh;q=0.7, ru;q=0.6") == "zh"
    assert parse_accept_language("en;q=0.2, ru;q=0.8") == "ru"

    # Unsupported languages return None
    assert parse_accept_language("fr-FR,fr;q=0.9,es;q=0.8") is None
    assert parse_accept_language("") is None
    assert parse_accept_language(None) is None
    assert parse_accept_language("*") is None


def test_t_function_fallbacks_and_formatting():
    """Test t() helper with dot notation, formatting kwargs, and Russian fallback."""
    # Direct Russian lookup
    assert t("nav.explorer", lang="ru") == "Live Explorer"
    assert t("catalog.badge", lang="ru") == "Каталог серверов"

    # Direct English lookup
    assert t("catalog.badge", lang="en") == "Server Catalog"
    assert t("hero.search_button", lang="en") == "Check Server"

    # Direct German lookup
    assert t("catalog.badge", lang="de") == "Serverkatalog"

    # Direct Chinese lookup
    assert t("catalog.badge", lang="zh") == "服务器大厅"

    # Formatting kwargs
    assert t("search.options_count", lang="ru", count=7) == "7 вариантов"
    assert t("search.options_count", lang="en", count=7) == "7 options"

    # Fallback to Russian when key is nonexistent in target lang
    assert t("this.key.definitely.does.not.exist", lang="en", default="Fallback") == "Fallback"


@pytest.mark.asyncio
async def test_set_lang_endpoint(client):
    """Verify /set-lang/{code} sets vv_lang cookie and redirects."""
    # Switch to English
    res_en = await client.get("/set-lang/en", follow_redirects=False)
    assert res_en.status_code == 303
    assert "vv_lang=en" in res_en.headers.get("set-cookie", "")

    # Switch to Chinese
    res_zh = await client.get("/set-lang/zh", follow_redirects=False)
    assert res_zh.status_code == 303
    assert "vv_lang=zh" in res_zh.headers.get("set-cookie", "")

    # Switch to German
    res_de = await client.get("/set-lang/de", follow_redirects=False)
    assert res_de.status_code == 303
    assert "vv_lang=de" in res_de.headers.get("set-cookie", "")

    # Invalid language code falls back to 'ru'
    res_inv = await client.get("/set-lang/invalid", follow_redirects=False)
    assert res_inv.status_code == 303
    assert "vv_lang=ru" in res_inv.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_page_renders_in_selected_language(client):
    """Verify templates render localized strings according to language cookie."""
    # 1. Russian (default)
    res_ru = await client.get("/")
    assert res_ru.status_code == 200
    assert "Популярные игровые сети" in res_ru.text
    assert "Каталог серверов" in res_ru.text
    assert "Все издания" in res_ru.text

    # 2. English via Cookie header
    res_en = await client.get("/", headers={"Cookie": "vv_lang=en"})
    assert res_en.status_code == 200
    assert "Popular Gaming Networks" in res_en.text
    assert "Server Catalog" in res_en.text
    assert "All Editions" in res_en.text

    # 3. German via Cookie header
    res_de = await client.get("/", headers={"Cookie": "vv_lang=de"})
    assert res_de.status_code == 200
    assert "Beliebte Gaming-Netzwerke" in res_de.text
    assert "Serverkatalog" in res_de.text

    # 4. Chinese via Cookie header
    res_zh = await client.get("/", headers={"Cookie": "vv_lang=zh"})
    assert res_zh.status_code == 200
    assert "热门游戏网络" in res_zh.text
    assert "服务器大厅" in res_zh.text

    # 5. Query param override (?lang=en)
    res_query = await client.get("/?lang=en")
    assert res_query.status_code == 200
    assert "Popular Gaming Networks" in res_query.text
    assert "vv_lang=en" in res_query.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_server_detail_page_localization(client):
    """Verify server detail page renders localized strings."""
    # English detail page
    res = await client.get("/server/mc.hypixel.net?mock=true", headers={"Cookie": "vv_lang=en"})
    assert res.status_code == 200
    assert "Play in Launcher" in res.text
    assert "Copy IP" in res.text
    assert "Online Players" in res.text
    assert "Peak Record" in res.text

    # German detail page
    res_de = await client.get("/server/mc.hypixel.net?mock=true", headers={"Cookie": "vv_lang=de"})
    assert res_de.status_code == 200
    assert "Im Launcher spielen" in res_de.text
    assert "IP kopieren" in res_de.text
