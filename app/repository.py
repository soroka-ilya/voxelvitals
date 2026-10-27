"""Repository layer for servers and telemetry history."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.database import get_db_connection
from app.domain.models import ServerStatus, TelemetryPoint


class ServerRepository:
    """Async repository for server metadata and time-series telemetry."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    async def get_or_create_server(
        self, address: str, edition: str = "java", is_pinned: bool = False
    ) -> int:
        """Fetch existing server ID or create a new entry."""
        now = datetime.now(timezone.utc).isoformat()
        normalized_addr = address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM servers WHERE LOWER(address) = ?", (normalized_addr,)
            )
            row = await cursor.fetchone()
            if row:
                server_id = row["id"]
                await conn.execute(
                    "UPDATE servers SET last_seen = ? WHERE id = ?",
                    (now, server_id),
                )
                await conn.commit()
                return server_id

            cursor = await conn.execute(
                """
                INSERT INTO servers (address, edition, first_seen, last_seen, is_pinned)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_addr, edition, now, now, 1 if is_pinned else 0),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_all_servers(self) -> List[dict]:
        """Return all tracked servers."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, address, edition, first_seen, last_seen, is_pinned FROM servers ORDER BY is_pinned DESC, last_seen DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def record_telemetry(self, server_id: int, status: ServerStatus) -> None:
        """Record a single telemetry point for a server."""
        now = datetime.now(timezone.utc).isoformat()
        async with get_db_connection(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO telemetry_history 
                (server_id, timestamp, players_online, players_max, ping_ms, is_online)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    server_id,
                    now,
                    status.players_online,
                    status.players_max,
                    status.latency_ms,
                    1 if status.is_online else 0,
                ),
            )
            await conn.commit()

    async def get_24h_history(
        self, server_id: int, hours: int = 24
    ) -> List[TelemetryPoint]:
        """Fetch telemetry points within the last N hours."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT timestamp, players_online, players_max, ping_ms, is_online
                FROM telemetry_history
                WHERE server_id = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (server_id, cutoff),
            )
            rows = await cursor.fetchall()
            return [
                TelemetryPoint(
                    timestamp=r["timestamp"],
                    players_online=r["players_online"],
                    players_max=r["players_max"],
                    ping_ms=r["ping_ms"],
                    is_online=bool(r["is_online"]),
                )
                for r in rows
            ]

    async def prune_old_telemetry(self, hours: int = 24) -> int:
        """Delete telemetry points older than retention window."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM telemetry_history WHERE timestamp < ?", (cutoff,)
            )
            await conn.commit()
            return cursor.rowcount

    # ----------------- User Auth & Sessions -----------------
    async def create_user(
        self, username: str, password_hash: str, mc_nickname: str = "", email: str = "", role: str = "user"
    ) -> int:
        """Create a new user account."""
        now = datetime.now(timezone.utc).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO users (username, password_hash, mc_nickname, email, role, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (username.strip(), password_hash, mc_nickname.strip() or username.strip(), email.strip(), role, now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_user_by_username(self, username: str) -> Optional[dict]:
        """Fetch user by case-insensitive username."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = ?",
                (username.strip().lower(),),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_id(self, user_id: int) -> Optional[dict]:
        """Fetch user by id."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_session(self, token: str, user_id: int, duration_days: int = 30) -> str:
        """Store active session token."""
        expires = (datetime.now(timezone.utc) + timedelta(days=duration_days)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO user_sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
                (token, user_id, expires),
            )
            await conn.commit()
            return token

    async def get_user_by_session(self, token: str) -> Optional[dict]:
        """Fetch user by valid non-expired session token."""
        now = datetime.now(timezone.utc).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT u.* FROM users u
                JOIN user_sessions s ON u.id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token, now),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def delete_session(self, token: str) -> None:
        """Invalidate session token."""
        async with get_db_connection(self.db_path) as conn:
            await conn.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            await conn.commit()

    # ----------------- Server News -----------------
    async def add_news(
        self, server_address: str, title: str, content: str, tag: str = "Обновление", author: str = "Администрация"
    ) -> int:
        """Add news announcement for a server."""
        now = datetime.now(timezone.utc).isoformat()
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO server_news (server_address, title, content, tag, author, published_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_addr, title.strip(), content.strip(), tag.strip(), author.strip(), now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_news_for_server(self, server_address: str, limit: int = 10) -> List[dict]:
        """Fetch latest news for a server."""
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT id, server_address, title, content, tag, author, published_at, is_pinned
                FROM server_news
                WHERE LOWER(server_address) = ?
                ORDER BY is_pinned DESC, published_at DESC
                LIMIT ?
                """,
                (clean_addr, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ----------------- Server Reviews -----------------
    async def add_review(
        self, server_address: str, author_name: str, rating: int, comment: str, user_id: Optional[int] = None
    ) -> int:
        """Add a review with 1-5 rating."""
        now = datetime.now(timezone.utc).isoformat()
        clean_addr = server_address.strip().lower()
        rating = max(1, min(5, rating))
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO server_reviews (server_address, user_id, author_name, rating, comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (clean_addr, user_id, author_name.strip(), rating, comment.strip(), now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_reviews_for_server(self, server_address: str, limit: int = 30) -> List[dict]:
        """Fetch reviews for a server."""
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT id, server_address, user_id, author_name, rating, comment, created_at, likes
                FROM server_reviews
                WHERE LOWER(server_address) = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (clean_addr, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_server_rating_stats(self, server_address: str) -> dict:
        """Compute average rating and count for a server."""
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT AVG(rating) as avg_rating, COUNT(*) as total_count
                FROM server_reviews
                WHERE LOWER(server_address) = ?
                """,
                (clean_addr,),
            )
            row = await cursor.fetchone()
            if row and row["total_count"] > 0:
                return {
                    "avg_rating": round(float(row["avg_rating"]), 1),
                    "total_count": int(row["total_count"]),
                }
            return {"avg_rating": 5.0, "total_count": 0}

    # ----------------- Server Votes -----------------
    async def vote_server(self, server_address: str, ip_hash: str) -> bool:
        """Cast a vote for a server (once per 24h per IP)."""
        now = datetime.now(timezone.utc).isoformat()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id FROM server_votes WHERE server_address = ? AND ip_hash = ? AND voted_at > ?",
                (clean_addr, ip_hash, cutoff),
            )
            if await cursor.fetchone():
                return False
            await conn.execute(
                "INSERT INTO server_votes (server_address, ip_hash, voted_at) VALUES (?, ?, ?)",
                (clean_addr, ip_hash, now),
            )
            await conn.commit()
            return True

    async def get_votes_count(self, server_address: str) -> int:
        """Get total votes for a server."""
        clean_addr = server_address.strip().lower()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM server_votes WHERE server_address = ?",
                (clean_addr,),
            )
            row = await cursor.fetchone()
            return int(row["cnt"]) if row else 0
