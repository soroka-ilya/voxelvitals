"""Asynchronous Minecraft server pinger supporting Java and Bedrock editions."""

import asyncio
import logging
from typing import Optional
import httpx
from mcstatus import BedrockServer, JavaServer
from app.config import settings
from app.domain.models import PlayerSample, ServerStatus
from app.services.motd_formatter import format_motd_html, strip_minecraft_formatting

logger = logging.getLogger(__name__)


def _extract_motd_str(motd: any) -> str:
    """Extract raw MOTD text representation from mcstatus object."""
    if motd is None:
        return ""
    if hasattr(motd, "to_minecraft"):
        return motd.to_minecraft()
    if hasattr(motd, "to_plain"):
        return motd.to_plain()
    return str(motd)


def get_mock_server_status(
    address: str, is_online: bool = True, edition: str = "java"
) -> ServerStatus:
    """Generate realistic mock status for testing or offline demonstration."""
    if not is_online:
        return ServerStatus(
            address=address,
            is_online=False,
            edition=edition,
            error_message="Could not resolve or connect to server (timed out)",
        )

    motd = "§6§lVOXELVITALS §7| §aProduction Ready Status\n§eSurvival §7• §bMinigames §7• §dEconomy"
    return ServerStatus(
        address=address,
        is_online=True,
        edition=edition,
        players_online=1420,
        players_max=5000,
        players_sample=[
            PlayerSample(name="Notch", id="069a79f4-44e9-4726-a5be-fca90e38aaf5"),
            PlayerSample(name="Jeb_", id="853c80ef-3c37-49fd-aa49-938b674acd06"),
            PlayerSample(name="Dinnerbone", id="61699b2e-d327-4a01-9f1e-0ea8c3f06bc6"),
        ],
        version_name="Paper 1.21.1",
        version_protocol=767,
        latency_ms=24.5,
        motd_raw=motd,
        motd_html=format_motd_html(motd),
        motd_plain=strip_minecraft_formatting(motd),
        icon_base64=None,
    )


async def _query_http_fallback(
    address: str, is_bedrock: bool = False, timeout: float = 3.5
) -> Optional[ServerStatus]:
    """Resilient Tier-2 fallback query via public telemetry API (api.mcsrvstat.us)."""
    clean_addr = address.strip()
    edition = "bedrock" if is_bedrock else "java"
    url = f"https://api.mcsrvstat.us/{'bedrock/3/' if is_bedrock else '3/'}{clean_addr}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if not data.get("online"):
                return None

            motd_lines = data.get("motd", {}).get("raw", [])
            motd_str = "\n".join(motd_lines) if isinstance(motd_lines, list) else str(motd_lines or "")
            players = data.get("players", {})
            sample = []
            if "list" in players and isinstance(players["list"], list):
                sample = [
                    PlayerSample(name=p.get("name", str(p)), id=p.get("uuid", ""))
                    for p in players["list"]
                    if isinstance(p, dict)
                ]

            return ServerStatus(
                address=clean_addr,
                is_online=True,
                edition=edition,
                players_online=int(players.get("online", 0)),
                players_max=int(players.get("max", 0)),
                players_sample=sample,
                version_name=data.get("version", "Minecraft Server"),
                version_protocol=data.get("protocol", {}).get("version") if isinstance(data.get("protocol"), dict) else None,
                latency_ms=round(float(data.get("debug", {}).get("ping", 32.0)), 1) if isinstance(data.get("debug"), dict) else 32.0,
                motd_raw=motd_str,
                motd_html=format_motd_html(motd_str),
                motd_plain=strip_minecraft_formatting(motd_str),
                icon_base64=data.get("icon"),
            )
    except Exception as exc:
        logger.debug(f"HTTP fallback query failed for {clean_addr}: {exc}")
        return None


async def query_server(
    address: str,
    is_bedrock: bool = False,
    timeout: Optional[float] = None,
) -> ServerStatus:
    """Query live server with DNS SRV support and fallback handling."""
    effective_timeout = timeout or settings.query_timeout_seconds
    clean_addr = address.strip()
    edition = "bedrock" if is_bedrock else "java"

    try:
        if is_bedrock:
            # Bedrock UDP query
            server = BedrockServer.lookup(clean_addr)
            status = await asyncio.wait_for(
                server.async_status(), timeout=effective_timeout
            )
            motd_str = _extract_motd_str(status.motd)
            return ServerStatus(
                address=clean_addr,
                is_online=True,
                edition="bedrock",
                players_online=status.players.online,
                players_max=status.players.max,
                players_sample=[],
                version_name=status.version.name or "Bedrock",
                version_protocol=status.version.protocol,
                latency_ms=round(float(status.latency), 1),
                motd_raw=motd_str,
                motd_html=format_motd_html(motd_str),
                motd_plain=strip_minecraft_formatting(motd_str),
                icon_base64=None,
            )
        else:
            # Java TCP Server List Ping
            server = await asyncio.wait_for(
                JavaServer.async_lookup(clean_addr), timeout=effective_timeout
            )
            status = await asyncio.wait_for(
                server.async_status(), timeout=effective_timeout
            )
            motd_str = _extract_motd_str(status.motd)
            sample = []
            if status.players and status.players.sample:
                sample = [
                    PlayerSample(name=p.name, id=str(p.id))
                    for p in status.players.sample
                ]
            return ServerStatus(
                address=clean_addr,
                is_online=True,
                edition="java",
                players_online=status.players.online if status.players else 0,
                players_max=status.players.max if status.players else 0,
                players_sample=sample,
                version_name=status.version.name if status.version else "Unknown",
                version_protocol=status.version.protocol if status.version else None,
                latency_ms=round(float(status.latency), 1),
                motd_raw=motd_str,
                motd_html=format_motd_html(motd_str),
                motd_plain=strip_minecraft_formatting(motd_str),
                icon_base64=status.icon,
            )
    except Exception as exc:
        logger.warning(f"Tier-1 query failed for {clean_addr}: {exc}. Trying Tier-2 fallback...")
        fallback_status = await _query_http_fallback(
            clean_addr, is_bedrock=is_bedrock, timeout=min(effective_timeout, 4.0)
        )
        if fallback_status:
            logger.info(f"Tier-2 fallback succeeded for {clean_addr} (players={fallback_status.players_online})")
            return fallback_status

        return ServerStatus(
            address=clean_addr,
            is_online=False,
            edition=edition,
            error_message=str(exc) or "Server offline or unreachable",
        )
