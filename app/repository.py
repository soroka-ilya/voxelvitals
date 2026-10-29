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

    async def get_user_by_google_id(self, google_id: str) -> Optional[dict]:
        """Fetch user by Google provider ID."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE google_id = ?", (str(google_id),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_microsoft_id(self, microsoft_id: str) -> Optional[dict]:
        """Fetch user by Microsoft/Xbox provider ID."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE microsoft_id = ?", (str(microsoft_id),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_user_by_email(self, email: str) -> Optional[dict]:
        """Fetch user by case-insensitive email."""
        if not email:
            return None
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute("SELECT * FROM users WHERE LOWER(email) = ?", (email.strip().lower(),))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_or_link_oauth_user(
        self,
        provider: str,
        provider_id: str,
        email: str = "",
        name: str = "",
        mc_nickname: str = "",
        avatar_url: str = "",
        is_verified_license: bool = False,
    ) -> dict:
        """Find existing user by provider_id or email, or create a new linked account."""
        now = datetime.now(timezone.utc).isoformat()
        clean_email = email.strip().lower() if email else ""
        col_id = "google_id" if provider == "google" else "microsoft_id"
        license_flag = 1 if is_verified_license else 0

        async with get_db_connection(self.db_path) as conn:
            # 1. Check if user already exists by provider_id
            cursor = await conn.execute(
                f"SELECT * FROM users WHERE {col_id} = ?", (str(provider_id),)
            )
            row = await cursor.fetchone()
            if row:
                user_id = row["id"]
                await conn.execute(
                    f"""
                    UPDATE users SET 
                        avatar_url = COALESCE(NULLIF(?, ''), avatar_url),
                        mc_nickname = CASE WHEN ? != '' THEN ? ELSE mc_nickname END,
                        is_verified_license = MAX(is_verified_license, ?)
                    WHERE id = ?
                    """,
                    (avatar_url, mc_nickname, mc_nickname, license_flag, user_id),
                )
                await conn.commit()
                return await self.get_user_by_id(user_id)

            # 2. Check if user exists by email
            if clean_email:
                cursor = await conn.execute(
                    "SELECT * FROM users WHERE LOWER(email) = ?", (clean_email,)
                )
                row = await cursor.fetchone()
                if row:
                    user_id = row["id"]
                    await conn.execute(
                        f"""
                        UPDATE users SET 
                            {col_id} = ?,
                            avatar_url = COALESCE(NULLIF(avatar_url, ''), ?),
                            mc_nickname = CASE WHEN ? != '' THEN ? ELSE mc_nickname END,
                            is_verified_license = MAX(is_verified_license, ?)
                        WHERE id = ?
                        """,
                        (str(provider_id), avatar_url, mc_nickname, mc_nickname, license_flag, user_id),
                    )
                    await conn.commit()
                    return await self.get_user_by_id(user_id)

            # 3. Create new user account
            base_name = mc_nickname or name or (clean_email.split("@")[0] if clean_email else f"{provider}_user")
            clean_username = "".join(c for c in base_name if c.isalnum() or c in ("_", "-")).strip() or "user"
            username = clean_username[:24]

            suffix = 0
            while True:
                candidate = username if suffix == 0 else f"{username}_{suffix}"
                c = await conn.execute("SELECT id FROM users WHERE LOWER(username) = ?", (candidate.lower(),))
                if not await c.fetchone():
                    username = candidate
                    break
                suffix += 1

            cursor = await conn.execute(
                f"""
                INSERT INTO users (
                    username, email, password_hash, mc_nickname, role, 
                    {col_id}, avatar_url, is_verified_license, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    clean_email or None,
                    f"oauth_{provider}",
                    mc_nickname or username,
                    "user",
                    str(provider_id),
                    avatar_url or "",
                    license_flag,
                    now,
                ),
            )
            await conn.commit()
            return await self.get_user_by_id(cursor.lastrowid)

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

    # ----------------- Site Analytics & Visitor Telemetry -----------------
    async def record_pageview(
        self,
        visitor_id: str,
        path: str,
        server_address: Optional[str] = None,
        page_title: str = "",
        referrer: str = "",
        device_type: str = "desktop",
        browser: str = "Other",
        ip_hash: str = "",
    ) -> int:
        """Log visitor page view."""
        now = datetime.now(timezone.utc).isoformat()
        clean_server = server_address.strip().lower() if server_address else None
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO analytics_pageviews
                (visitor_id, path, server_address, page_title, referrer, device_type, browser, ip_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (visitor_id, path, clean_server, page_title, referrer, device_type, browser, ip_hash, now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def record_search(
        self,
        visitor_id: str,
        query: str,
        edition: str = "java",
        results_count: int = 0,
        matched_server: Optional[str] = None,
    ) -> int:
        """Log visitor search query."""
        now = datetime.now(timezone.utc).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO analytics_searches
                (visitor_id, query, edition, results_count, matched_server, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (visitor_id, query.strip(), edition, results_count, matched_server, now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def record_event(
        self,
        visitor_id: str,
        event_type: str,
        target: Optional[str] = None,
        metadata: Optional[str] = None,
    ) -> int:
        """Log client-side user interactive action."""
        now = datetime.now(timezone.utc).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                INSERT INTO analytics_events
                (visitor_id, event_type, target, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (visitor_id, event_type.strip(), target, metadata, now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_analytics_summary(self, hours: int = 24) -> dict:
        """Calculate high-level KPI metrics for the specified timeframe."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT COUNT(*) as total_pv, COUNT(DISTINCT visitor_id) as uniq_visitors
                FROM analytics_pageviews
                WHERE created_at >= ?
                """,
                (cutoff,),
            )
            pv_row = await cursor.fetchone()
            total_pv = int(pv_row["total_pv"]) if pv_row else 0
            uniq_visitors = int(pv_row["uniq_visitors"]) if pv_row else 0

            cursor = await conn.execute(
                "SELECT COUNT(*) as total_searches FROM analytics_searches WHERE created_at >= ?",
                (cutoff,),
            )
            s_row = await cursor.fetchone()
            total_searches = int(s_row["total_searches"]) if s_row else 0

            cursor = await conn.execute(
                """
                SELECT COUNT(*) as conversions FROM analytics_events 
                WHERE created_at >= ? AND event_type IN ('copy_ip', 'launch_client')
                """,
                (cutoff,),
            )
            c_row = await cursor.fetchone()
            conversions = int(c_row["conversions"]) if c_row else 0

            return {
                "total_pageviews": total_pv,
                "unique_visitors": uniq_visitors,
                "total_searches": total_searches,
                "total_conversions": conversions,
            }

    async def get_top_searches(self, limit: int = 20, hours: int = 24) -> list:
        """Fetch most frequently searched queries with hit counts."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT query, COUNT(*) as count, MAX(created_at) as last_searched, MAX(matched_server) as matched_server
                FROM analytics_searches
                WHERE created_at >= ?
                GROUP BY LOWER(query)
                ORDER BY count DESC
                LIMIT ?
                """,
                (cutoff, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_top_viewed_servers(self, limit: int = 10, hours: int = 24) -> list:
        """Fetch most viewed server detail pages."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT server_address, COUNT(*) as view_count, MAX(created_at) as last_viewed
                FROM analytics_pageviews
                WHERE server_address IS NOT NULL AND server_address != '' AND created_at >= ?
                GROUP BY LOWER(server_address)
                ORDER BY view_count DESC
                LIMIT ?
                """,
                (cutoff, limit),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_recent_activity_stream(self, limit: int = 30) -> list:
        """Fetch unified chronological visitor activity stream."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                """
                SELECT 'pageview' as category, path as item, server_address as extra, visitor_id, device_type, browser, created_at
                FROM analytics_pageviews
                UNION ALL
                SELECT 'search' as category, query as item, matched_server as extra, visitor_id, edition as device_type, '' as browser, created_at
                FROM analytics_searches
                UNION ALL
                SELECT 'event' as category, event_type as item, target as extra, visitor_id, metadata as device_type, '' as browser, created_at
                FROM analytics_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_device_and_browser_stats(self, hours: int = 24) -> dict:
        """Fetch device and browser distributions."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        async with get_db_connection(self.db_path) as conn:
            c1 = await conn.execute(
                "SELECT device_type, COUNT(*) as cnt FROM analytics_pageviews WHERE created_at >= ? GROUP BY device_type",
                (cutoff,),
            )
            devices = [dict(r) for r in await c1.fetchall()]

            c2 = await conn.execute(
                "SELECT browser, COUNT(*) as cnt FROM analytics_pageviews WHERE created_at >= ? GROUP BY browser",
                (cutoff,),
            )
            browsers = [dict(r) for r in await c2.fetchall()]

            c3 = await conn.execute(
                "SELECT event_type, COUNT(*) as cnt FROM analytics_events WHERE created_at >= ? GROUP BY event_type ORDER BY cnt DESC",
                (cutoff,),
            )
            events = [dict(r) for r in await c3.fetchall()]

            return {"devices": devices, "browsers": browsers, "events": events}
