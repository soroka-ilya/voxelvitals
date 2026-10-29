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

    # Base application URL for OAuth redirects (e.g. http://localhost:8000 or https://voxelvitals.com)
    base_url: str = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")

    # Google OAuth 2.0 Settings
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "")

    # Microsoft / Xbox OAuth Settings
    microsoft_client_id: str = os.getenv("MICROSOFT_CLIENT_ID", "")
    microsoft_client_secret: str = os.getenv("MICROSOFT_CLIENT_SECRET", "")
    microsoft_redirect_uri: str = os.getenv("MICROSOFT_REDIRECT_URI", "")

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
