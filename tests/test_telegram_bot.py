"""Unit and integration tests for Telegram bot webhook processing."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from app.database import init_db
from app.main import app
from app.services.tg_service import process_telegram_update


@pytest_asyncio.fixture
async def client():
    """Create async test client with initialized database."""
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_telegram_start_help():
    """Verify /start and /help return welcome message with links."""
    update = {
        "update_id": 1001,
        "message": {
            "message_id": 1,
            "chat": {"id": 12345678},
            "text": "/start",
        },
    }
    resp = await process_telegram_update(update)
    assert resp is not None
    assert resp["method"] == "sendMessage"
    assert resp["chat_id"] == 12345678
    assert "VoxelVitals" in resp["text"]
    assert "/status" in resp["text"]


@pytest.mark.asyncio
async def test_telegram_top_servers():
    """Verify /top returns catalog list."""
    update = {
        "update_id": 1002,
        "message": {
            "message_id": 2,
            "chat": {"id": 12345678},
            "text": "/top",
        },
    }
    resp = await process_telegram_update(update)
    assert resp is not None
    assert "Популярные серверы" in resp["text"]
    assert "voxelvitals.ru/server" in resp["text"]


@pytest.mark.asyncio
async def test_telegram_status_command():
    """Verify /status mc.hypixel.net queries server and returns markdown info."""
    update = {
        "update_id": 1003,
        "message": {
            "message_id": 3,
            "chat": {"id": 999888},
            "text": "/status mc.hypixel.net",
        },
    }
    resp = await process_telegram_update(update)
    assert resp is not None
    assert resp["chat_id"] == 999888
    assert "mc.hypixel.net" in resp["text"]
    assert "voxelvitals.ru/server/mc.hypixel.net" in resp["text"]


@pytest.mark.asyncio
async def test_telegram_ping_command():
    """Verify /ping mc.hypixel.net returns 3 regional probe benchmarks."""
    update = {
        "update_id": 1004,
        "message": {
            "message_id": 4,
            "chat": {"id": 999888},
            "text": "/ping mc.hypixel.net",
        },
    }
    resp = await process_telegram_update(update)
    assert resp is not None
    assert "Москва" in resp["text"]
    assert "Франкфурт" in resp["text"]
    assert "Хельсинки" in resp["text"]


@pytest.mark.asyncio
async def test_telegram_webhook_http_endpoint(client):
    """Verify POST /api/tg/webhook returns JSON response with message."""
    payload = {
        "update_id": 2001,
        "message": {
            "message_id": 10,
            "chat": {"id": 445566},
            "text": "/record hypixel",
        },
    }
    res = await client.post("/api/tg/webhook", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data.get("method") == "sendMessage"
    assert data.get("chat_id") == 445566
    assert "216,478" in data.get("text", "")
