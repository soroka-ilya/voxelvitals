"""Database initialization and connection management using aiosqlite."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
import aiosqlite
from app.config import settings

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT UNIQUE NOT NULL,
    edition TEXT NOT NULL DEFAULT 'java',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    is_pinned INTEGER NOT NULL DEFAULT 0,
    peak_players INTEGER NOT NULL DEFAULT 0,
    peak_online INTEGER NOT NULL DEFAULT 0,
    peak_date TEXT,
    peak_players_time TEXT
);

CREATE TABLE IF NOT EXISTS telemetry_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id INTEGER NOT NULL,
    timestamp TEXT NOT NULL,
    players_online INTEGER NOT NULL DEFAULT 0,
    players_max INTEGER NOT NULL DEFAULT 0,
    ping_ms REAL NOT NULL DEFAULT 0.0,
    is_online INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (server_id) REFERENCES servers(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_servers_address ON servers(address);
CREATE INDEX IF NOT EXISTS idx_telemetry_server_ts ON telemetry_history(server_id, timestamp);
"""


@asynccontextmanager
async def get_db_connection(db_path: str = None) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an async connection to the SQLite database with busy timeout and FK enforcement."""
    target_path = db_path or settings.db_path
    async with aiosqlite.connect(target_path, timeout=30.0) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA busy_timeout=15000;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        yield conn


async def init_db(db_path: str = None) -> None:
    """Create stateless server telemetry tables and drop legacy personal-data/UGC tables."""
    async with get_db_connection(db_path) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.executescript(CREATE_TABLES_SQL)
        # Drop any legacy personal-data, UGC, or visitor-analytics tables if present
        for legacy_table in (
            "user_sessions",
            "users",
            "server_news",
            "server_reviews",
            "server_votes",
            "analytics_pageviews",
            "analytics_searches",
            "analytics_events",
        ):
            await conn.execute(f"DROP TABLE IF EXISTS {legacy_table}")

        # Migrate servers table for peak records
        cursor_s = await conn.execute("PRAGMA table_info(servers)")
        server_cols = {row["name"] for row in await cursor_s.fetchall()}
        if "peak_players" not in server_cols:
            await conn.execute("ALTER TABLE servers ADD COLUMN peak_players INTEGER NOT NULL DEFAULT 0")
        if "peak_online" not in server_cols:
            await conn.execute("ALTER TABLE servers ADD COLUMN peak_online INTEGER NOT NULL DEFAULT 0")
        if "peak_date" not in server_cols:
            await conn.execute("ALTER TABLE servers ADD COLUMN peak_date TEXT")
        if "peak_players_time" not in server_cols:
            await conn.execute("ALTER TABLE servers ADD COLUMN peak_players_time TEXT")

        await conn.commit()
