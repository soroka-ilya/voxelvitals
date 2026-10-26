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
    is_pinned INTEGER NOT NULL DEFAULT 0
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
    """Yield an async connection to the SQLite database with WAL mode."""
    target_path = db_path or settings.db_path
    async with aiosqlite.connect(target_path) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys=ON;")
        yield conn


async def init_db(db_path: str = None) -> None:
    """Create tables and indexes if they do not exist."""
    async with get_db_connection(db_path) as conn:
        await conn.executescript(CREATE_TABLES_SQL)
        await conn.commit()
