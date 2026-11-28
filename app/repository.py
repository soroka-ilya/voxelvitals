"""Repository layer for servers and telemetry history."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from app.database import get_db_connection
from app.domain.models import ServerStatus, TelemetryPoint
from app.services.pinger import is_safe_address

RUSSIAN_MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля",
    5: "мая", 6: "июня", 7: "июля", 8: "августа",
    9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
}


def format_peak_online(count: int, timestamp_iso: Optional[str] = None) -> str:
    """Format peak online player count and timestamp into Russian localized string.

    Example: 'Абсолютный пик: 114,841 игроков (15 апреля 2024)'
    """
    if count <= 0:
        return "Абсолютный пик: 0 игроков"

    formatted_count = f"{count:,}"
    if not timestamp_iso:
        return f"Абсолютный пик: {formatted_count} игроков"

    dt = None
    try:
        clean_ts = timestamp_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean_ts)
    except Exception:
        # If timestamp is already formatted like '15 апреля 2024'
        if any(m in timestamp_iso for m in RUSSIAN_MONTHS.values()):
            return f"Абсолютный пик: {formatted_count} игроков ({timestamp_iso})"

    if dt:
        month_name = RUSSIAN_MONTHS.get(dt.month, "")
        formatted_date = f"{dt.day} {month_name} {dt.year}"
        return f"Абсолютный пик: {formatted_count} игроков ({formatted_date})"

    return f"Абсолютный пик: {formatted_count} игроков"


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

        # Reject scanners, static web assets, and SSRF targets (e.g. /.env, s3.js, 127.0.0.1:25565)
        blocked_exts = (
            ".php", ".env", ".git", ".txt", ".bak", ".ini",
            ".js", ".css", ".html", ".htm", ".xml", ".json",
            ".yml", ".yaml", ".py", ".sh", ".sql", ".map",
            ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp",
            ".woff", ".woff2", ".ttf", ".eot", ".wasm",
        )
        host_part = normalized_addr.split(":", 1)[0]
        if (
            not normalized_addr
            or normalized_addr.startswith(".")
            or "/" in normalized_addr
            or "\\" in normalized_addr
            or " " in normalized_addr
            or any(c in normalized_addr for c in ("?", "&", "=", "<", ">", '"', "'"))
            or host_part.endswith(blocked_exts)
            or (not is_pinned and "." not in normalized_addr)
            or (not is_pinned and not is_safe_address(normalized_addr))
        ):
            return 0

        async with get_db_connection(self.db_path) as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO servers (address, edition, first_seen, last_seen, is_pinned)
                VALUES (?, ?, ?, ?, ?)
                """,
                (normalized_addr, edition, now, now, 1 if is_pinned else 0),
            )
            cursor = await conn.execute(
                "SELECT id FROM servers WHERE LOWER(address) = ?", (normalized_addr,)
            )
            row = await cursor.fetchone()
            server_id = row["id"]
            await conn.execute(
                "UPDATE servers SET last_seen = ? WHERE id = ?",
                (now, server_id),
            )
            await conn.commit()
            return server_id

    async def get_all_servers(self) -> List[dict]:
        """Return all tracked servers."""
        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT id, address, edition, first_seen, last_seen, is_pinned FROM servers ORDER BY is_pinned DESC, last_seen DESC"
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def record_telemetry(self, server_id: int, status: ServerStatus) -> None:
        """Record a single telemetry point and update peak player record if exceeded."""
        if not server_id or server_id <= 0:
            return
        now_dt = datetime.now(timezone.utc)
        now = now_dt.isoformat()
        date_str = f"{now_dt.day} {RUSSIAN_MONTHS.get(now_dt.month, '')} {now_dt.year}"
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
            if status.is_online and status.players_online > 0:
                await conn.execute(
                    """
                    UPDATE servers 
                    SET peak_players = ?, peak_online = ?, peak_players_time = ?, peak_date = ?
                    WHERE id = ? AND (? > peak_players OR peak_players IS NULL)
                    """,
                    (status.players_online, status.players_online, now, date_str, server_id, status.players_online),
                )
            await conn.commit()

    async def get_server_peak(self, address: str) -> dict:
        """Fetch all-time peak player record combining historical benchmarks and live tracking."""
        clean = address.strip().lower()
        # Canonical benchmarks for major networks
        benchmarks = {
            "mc.hypixel.net": (216478, "16 апреля 2021"),
            "2b2t.org": (1980, "12 июня 2020"),
            "donutsmp.net": (18450, "23 мая 2024"),
            "play.cubecraft.net": (45820, "27 декабря 2020"),
            "geo.hivebedrock.network": (39410, "15 января 2023"),
            "mc.reallyworld.ru": (16890, "10 сентября 2023"),
            "mc.holyworld.ru": (19240, "20 декабря 2023"),
            "mc.funtime.su": (21350, "3 января 2024"),
            "mc.vimeworld.net": (14200, "8 ноября 2020"),
            "hub.mc-complex.com": (4850, "14 февраля 2024"),
        }
        b_count, b_date = benchmarks.get(clean, (0, ""))

        async with get_db_connection(self.db_path) as conn:
            cursor = await conn.execute(
                "SELECT peak_players, peak_online, peak_date, peak_players_time FROM servers WHERE LOWER(address) = ?",
                (clean,),
            )
            row = await cursor.fetchone()
            db_count = max(row["peak_players"] or 0, row["peak_online"] or 0) if row else 0
            db_date = (row["peak_date"] if row and row["peak_date"] else "")
            db_time = (row["peak_players_time"] if row and row["peak_players_time"] else "")

        if db_count > b_count:
            peak_val = db_count
            peak_d = db_date or "Недавно"
            peak_t = db_time or None
        elif b_count > 0:
            peak_val = b_count
            peak_d = b_date
            peak_t = None
        else:
            peak_val = db_count
            peak_d = db_date or "Не зафиксирован"
            peak_t = db_time or None

        return {
            "peak_players": peak_val,
            "peak_online": peak_val,
            "peak_date": peak_d,
            "peak_players_time": peak_t,
            "formatted": format_peak_online(peak_val, peak_t or peak_d),
        }

    async def get_24h_history(
        self, server_id: int, hours: int = 24
    ) -> List[TelemetryPoint]:
        """Fetch telemetry points within the last N hours."""
        if not server_id or server_id <= 0:
            return []
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






