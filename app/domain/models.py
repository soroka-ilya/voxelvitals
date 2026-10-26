"""Pydantic domain models for VoxelVitals."""

from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field


class PlayerSample(BaseModel):
    """Player sample entry from server query."""

    name: str
    id: str = ""


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
