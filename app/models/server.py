"""Pydantic models for server status, regional latencies, and telemetry."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class PlayerSample(BaseModel):
    """Player sample entry from server query."""

    name: str
    id: str = ""


class RegionalLatency(BaseModel):
    """Latency metrics from geographic probe locations."""

    moscow: float = 0.0
    frankfurt: float = 0.0
    helsinki: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {"moscow": self.moscow, "frankfurt": self.frankfurt, "helsinki": self.helsinki}


class ServerStatus(BaseModel):
    """Normalized Minecraft server status representation."""

    address: str
    is_online: bool
    edition: str = "java"  # 'java' or 'bedrock'
    players_online: int = 0
    players_max: int = 0
    players_sample: List[PlayerSample] = Field(default_factory=list)
    version_name: str = "Unknown"
    version_protocol: Optional[int] = None
    latency_ms: float = 0.0
    motd_raw: str = ""
    motd_html: str = ""
    motd_plain: str = ""
    icon_base64: Optional[str] = None
    last_updated: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    error_message: Optional[str] = None

    @field_validator("icon_base64", mode="before")
    @classmethod
    def validate_icon(cls, v):
        """Sanitize and validate server icon data URI."""
        if not v or not isinstance(v, str):
            return None
        # Enforce max length of 256 KB
        if len(v) > 262144:
            return None
        safe_prefixes = (
            "data:image/png;base64,",
            "data:image/jpeg;base64,",
            "data:image/svg+xml;base64,",
            "data:image/webp;base64,",
        )
        if not any(v.startswith(prefix) for prefix in safe_prefixes):
            return None
        return v

    # Multi-Region Latency Probes (R2)
    region_latencies: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"moscow": 0.0, "frankfurt": 0.0, "helsinki": 0.0}
    )
    regional_latencies: Optional[Dict[str, float]] = None

    # Peak Online Hall of Fame (R5)
    peak_players: int = 0
    peak_online: int = 0
    peak_date: Optional[str] = None
    peak_players_time: Optional[str] = None
    peak_players_formatted: Optional[str] = None


class TelemetryPoint(BaseModel):
    """Historical telemetry record for a server."""

    timestamp: str
    players_online: int
    players_max: int
    ping_ms: float
    is_online: bool


class BadgeConfig(BaseModel):
    """Options for rendering SVG status badges."""

    label: str = "minecraft"
    style: str = "flat"  # flat | plastic
    show_ping: bool = True
