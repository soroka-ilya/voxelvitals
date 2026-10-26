"""Unit tests for SQLite repository and telemetry history."""

import os
import tempfile
import pytest
import pytest_asyncio
from app.database import init_db
from app.domain.models import ServerStatus
from app.repository import ServerRepository


@pytest_asyncio.fixture
async def temp_repo():
    """Create isolated temporary database repository for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    await init_db(path)
    repo = ServerRepository(db_path=path)
    yield repo
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_get_or_create_server(temp_repo):
    """Verify idempotent creation and retrieval of server records."""
    s1_id = await temp_repo.get_or_create_server("mc.hypixel.net", edition="java")
    assert s1_id > 0

    # Repeat call should return the same server id
    s2_id = await temp_repo.get_or_create_server("MC.HYPIXEL.NET", edition="java")
    assert s1_id == s2_id

    servers = await temp_repo.get_all_servers()
    assert len(servers) == 1
    assert servers[0]["address"] == "mc.hypixel.net"


@pytest.mark.asyncio
async def test_record_and_get_history(temp_repo):
    """Verify recording telemetry points and retrieving 24h history."""
    server_id = await temp_repo.get_or_create_server("donutsmp.net")
    
    status1 = ServerStatus(
        address="donutsmp.net",
        is_online=True,
        players_online=3500,
        players_max=10000,
        latency_ms=18.5,
    )
    await temp_repo.record_telemetry(server_id, status1)

    status2 = ServerStatus(
        address="donutsmp.net",
        is_online=True,
        players_online=3620,
        players_max=10000,
        latency_ms=19.1,
    )
    await temp_repo.record_telemetry(server_id, status2)

    history = await temp_repo.get_24h_history(server_id, hours=24)
    assert len(history) == 2
    assert history[0].players_online == 3500
    assert history[1].players_online == 3620
    assert history[0].ping_ms == 18.5


@pytest.mark.asyncio
async def test_prune_old_telemetry(temp_repo):
    """Verify pruning points older than specified hours."""
    from datetime import datetime, timedelta, timezone
    from app.database import get_db_connection

    server_id = await temp_repo.get_or_create_server("prune.test")
    # Insert an old entry (30 hours ago)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    async with get_db_connection(temp_repo.db_path) as conn:
        await conn.execute(
            """
            INSERT INTO telemetry_history 
            (server_id, timestamp, players_online, players_max, ping_ms, is_online)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (server_id, old_time, 100, 200, 30.0, 1),
        )
        await conn.commit()

    # Prune with 24h retention
    deleted = await temp_repo.prune_old_telemetry(hours=24)
    assert deleted == 1

    history = await temp_repo.get_24h_history(server_id, hours=48)
    assert len(history) == 0
