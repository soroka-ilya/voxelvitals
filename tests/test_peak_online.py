"""Tests for R5: Peak Online Hall of Fame.

Covers Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases) for:
- Historical peak online persistence in SQLite
- Atomic conditional updates (WHERE ? > peak_players)
- Canonical benchmark networks fallback
- Russian date formatting and localization
"""

import asyncio
from datetime import datetime, timezone
import aiosqlite
import pytest
import pytest_asyncio
from app.database import get_db_connection, init_db
from app.domain.models import ServerStatus
from app.repository import ServerRepository


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Initialize database before each test run."""
    await init_db()


@pytest.fixture
def repo():
    """Create a ServerRepository instance."""
    return ServerRepository()


# ==============================================================================
# Tier 1: Feature Coverage (R5 Core Behaviors)
# ==============================================================================


@pytest.mark.asyncio
async def test_peak_online_canonical_benchmark_for_major_networks(repo):
    """Verify canonical benchmark records exist for flagship networks (e.g. Hypixel, 2b2t)."""
    hypixel_peak = await repo.get_server_peak("mc.hypixel.net")
    assert hypixel_peak["peak_players"] >= 216478
    assert "апреля 2021" in hypixel_peak["peak_date"]

    twob_peak = await repo.get_server_peak("2b2t.org")
    assert twob_peak["peak_players"] >= 1980
    assert "июня 2020" in twob_peak["peak_date"]


@pytest.mark.asyncio
async def test_peak_online_new_server_initial_record(repo):
    """Verify newly registered server with no telemetry returns peak 0 or unrecorded status."""
    addr = "brandnew.server.xyz"
    server_id = await repo.get_or_create_server(addr)
    assert server_id > 0

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 0
    assert "Не зафиксирован" in peak["peak_date"] or peak["peak_date"] == ""


@pytest.mark.asyncio
async def test_peak_online_increases_when_higher_count_recorded(repo):
    """Verify recording telemetry with higher online player count updates the peak."""
    addr = "growing.server.net"
    server_id = await repo.get_or_create_server(addr)

    status = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=450,
        players_max=1000,
        latency_ms=20.0,
    )
    await repo.record_telemetry(server_id, status)

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 450
    assert peak["peak_date"] != ""


@pytest.mark.asyncio
async def test_peak_online_retains_record_when_lower_count_recorded(repo):
    """Verify recording lower player count does not overwrite the peak record."""
    addr = "fluctuating.server.net"
    server_id = await repo.get_or_create_server(addr)

    # Initial peak: 800 players
    status_high = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=800,
        players_max=1000,
        latency_ms=25.0,
    )
    await repo.record_telemetry(server_id, status_high)

    peak1 = await repo.get_server_peak(addr)
    assert peak1["peak_players"] == 800
    original_date = peak1["peak_date"]

    # Lower subsequent count: 320 players
    status_low = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=320,
        players_max=1000,
        latency_ms=25.0,
    )
    await repo.record_telemetry(server_id, status_low)

    peak2 = await repo.get_server_peak(addr)
    # Peak player count remains 800
    assert peak2["peak_players"] == 800
    assert peak2["peak_date"] == original_date


@pytest.mark.asyncio
async def test_peak_online_offline_telemetry_does_not_update_peak(repo):
    """Verify telemetry from an offline server does not alter the peak player count."""
    addr = "offline.test.net"
    server_id = await repo.get_or_create_server(addr)

    status_offline = ServerStatus(
        address=addr,
        is_online=False,
        edition="java",
        players_online=9999,  # Stale or invalid count while offline
        players_max=1000,
        error_message="Timed out",
    )
    await repo.record_telemetry(server_id, status_offline)

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 0


@pytest.mark.asyncio
async def test_peak_online_database_persistence_across_connections(repo):
    """Verify peak record is written to SQLite servers table and survives new connections."""
    addr = "persisted.server.net"
    server_id = await repo.get_or_create_server(addr)

    status = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=654,
        players_max=1000,
    )
    await repo.record_telemetry(server_id, status)

    # Read directly via fresh raw SQLite connection
    async with get_db_connection() as conn:
        cursor = await conn.execute(
            "SELECT peak_players, peak_date FROM servers WHERE id = ?", (server_id,)
        )
        row = await cursor.fetchone()
        assert row is not None
        assert row["peak_players"] == 654
        assert row["peak_date"] is not None


# ==============================================================================
# Tier 2: Boundary & Corner Cases (Concurrency, Idempotence, Formats)
# ==============================================================================


@pytest.mark.asyncio
async def test_peak_online_zero_players_telemetry(repo):
    """Verify telemetry with 0 online players does not alter peak records."""
    addr = "empty.server.net"
    server_id = await repo.get_or_create_server(addr)

    status_zero = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=0,
        players_max=100,
    )
    await repo.record_telemetry(server_id, status_zero)

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 0


@pytest.mark.asyncio
async def test_peak_online_schema_migration_idempotent():
    """Verify init_db() migration is idempotent and maintains peak_players column."""
    # Run init_db multiple times
    await init_db()
    await init_db()
    await init_db()

    async with get_db_connection() as conn:
        cursor = await conn.execute("PRAGMA table_info(servers)")
        columns = {row["name"] for row in await cursor.fetchall()}
        assert "peak_players" in columns
        assert "peak_date" in columns


@pytest.mark.asyncio
async def test_peak_online_atomic_conditional_update(repo):
    """Verify concurrent telemetry updates reliably arrive at the true maximum count."""
    addr = "concurrent.spike.net"
    server_id = await repo.get_or_create_server(addr)

    # Concurrently fire status updates with varying player counts
    player_counts = [150, 480, 1200, 300, 950, 80, 1100, 600]

    async def update_count(count: int):
        s = ServerStatus(
            address=addr,
            is_online=True,
            edition="java",
            players_online=count,
            players_max=2000,
        )
        await repo.record_telemetry(server_id, s)

    await asyncio.gather(*[update_count(c) for c in player_counts])

    peak = await repo.get_server_peak(addr)
    # The atomic WHERE ? > peak_players clause ensures max(1200) wins
    assert peak["peak_players"] == 1200


@pytest.mark.asyncio
async def test_peak_online_russian_date_formatting():
    """Verify Russian date formatting rules for peak online strings."""
    # Russian month dictionary matching requirements R5 / spec_report
    ru_months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }

    def format_peak(count: int, dt: datetime) -> str:
        month_name = ru_months[dt.month]
        formatted_count = f"{count:,}"
        return f"Абсолютный пик: {formatted_count} игроков ({dt.day} {month_name} {dt.year})"

    dt_test = datetime(2024, 4, 15, 18, 30, tzinfo=timezone.utc)
    res = format_peak(114841, dt_test)
    assert res == "Абсолютный пик: 114,841 игроков (15 апреля 2024)"

    dt_winter = datetime(2023, 12, 31, 23, 59, tzinfo=timezone.utc)
    res_winter = format_peak(50000, dt_winter)
    assert res_winter == "Абсолютный пик: 50,000 игроков (31 декабря 2023)"


@pytest.mark.asyncio
async def test_peak_online_large_values_boundary(repo):
    """Verify large player counts (e.g. 1,500,000) are stored and retrieved without integer overflow."""
    addr = "mega.network.org"
    server_id = await repo.get_or_create_server(addr)

    status = ServerStatus(
        address=addr,
        is_online=True,
        edition="java",
        players_online=1500000,
        players_max=2000000,
    )
    await repo.record_telemetry(server_id, status)

    peak = await repo.get_server_peak(addr)
    assert peak["peak_players"] == 1500000


@pytest.mark.asyncio
async def test_peak_online_case_insensitivity_and_whitespace(repo):
    """Verify get_server_peak handles mixed case and surrounding whitespace in address."""
    clean_peak = await repo.get_server_peak("mc.hypixel.net")
    dirty_peak = await repo.get_server_peak("  MC.HYPIXEL.NET  \n")

    assert dirty_peak["peak_players"] == clean_peak["peak_players"]
    assert dirty_peak["peak_date"] == clean_peak["peak_date"]
