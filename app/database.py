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

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT,
    password_hash TEXT,
    mc_nickname TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    google_id TEXT UNIQUE,
    microsoft_id TEXT UNIQUE,
    avatar_url TEXT,
    is_verified_license INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS server_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_address TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tag TEXT NOT NULL DEFAULT 'Обновление',
    author TEXT NOT NULL DEFAULT 'Администрация',
    published_at TEXT NOT NULL,
    is_pinned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS server_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_address TEXT NOT NULL,
    user_id INTEGER,
    author_name TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT NOT NULL,
    created_at TEXT NOT NULL,
    likes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS server_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_address TEXT NOT NULL,
    ip_hash TEXT NOT NULL,
    voted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_server_news_addr ON server_news(server_address);
CREATE INDEX IF NOT EXISTS idx_server_reviews_addr ON server_reviews(server_address);

CREATE TABLE IF NOT EXISTS analytics_pageviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id TEXT NOT NULL,
    path TEXT NOT NULL,
    server_address TEXT,
    page_title TEXT,
    referrer TEXT,
    device_type TEXT NOT NULL DEFAULT 'desktop',
    browser TEXT NOT NULL DEFAULT 'Other',
    ip_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_searches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id TEXT NOT NULL,
    query TEXT NOT NULL,
    edition TEXT NOT NULL DEFAULT 'java',
    results_count INTEGER NOT NULL DEFAULT 0,
    matched_server TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    target TEXT,
    metadata TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_analytics_pv_time ON analytics_pageviews(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_pv_server ON analytics_pageviews(server_address);
CREATE INDEX IF NOT EXISTS idx_analytics_search_time ON analytics_searches(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_search_query ON analytics_searches(query);
CREATE INDEX IF NOT EXISTS idx_analytics_events_time ON analytics_events(created_at);
CREATE INDEX IF NOT EXISTS idx_analytics_events_type ON analytics_events(event_type);
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
    """Create tables and indexes if they do not exist, and apply schema migrations."""
    async with get_db_connection(db_path) as conn:
        await conn.executescript(CREATE_TABLES_SQL)
        # Migrate existing database if OAuth columns are missing
        cursor = await conn.execute("PRAGMA table_info(users)")
        existing_cols = {row["name"] for row in await cursor.fetchall()}
        if "google_id" not in existing_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
        if "microsoft_id" not in existing_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN microsoft_id TEXT")
        if "avatar_url" not in existing_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
        if "is_verified_license" not in existing_cols:
            await conn.execute("ALTER TABLE users ADD COLUMN is_verified_license INTEGER NOT NULL DEFAULT 0")
        await conn.commit()
