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
