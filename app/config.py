"""Application configuration."""

import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Settings:
    """VoxelVitals settings container."""

    app_name: str = "VoxelVitals"
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    db_path: str = os.getenv("DB_PATH", "voxelvitals.db")
    poll_interval_seconds: int = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))
    history_retention_hours: int = 24
    query_timeout_seconds: float = float(os.getenv("QUERY_TIMEOUT_SECONDS", "5.0"))

    # Security & Environment flags
    enable_mock_auth: bool = os.getenv("ENABLE_MOCK_AUTH", "false").lower() in ("true", "1")
    enable_docs: bool = os.getenv("ENABLE_DOCS", "false").lower() in ("true", "1")
    telegram_webhook_secret: str = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
    trusted_proxies: List[str] = field(
        default_factory=lambda: [
            ip.strip() for ip in os.getenv("TRUSTED_PROXIES", "127.0.0.1,::1").split(",") if ip.strip()
        ]
    )

    # Default featured servers on homepage
    featured_servers: List[str] = field(
        default_factory=lambda: [
            "mc.hypixel.net",
            "play.cubecraft.net",
            "donutsmp.net",
            "play.manacube.com",
        ]
    )


settings = Settings()
