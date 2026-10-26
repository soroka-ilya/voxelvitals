"""REST JSON API and dynamic SVG badge endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query, Response
from app.domain.models import BadgeConfig, ServerStatus, TelemetryPoint
from app.repository import ServerRepository
from app.services.alias_service import resolve_address, search_suggestions
from app.services.badge_service import generate_status_badge
from app.services.pinger import get_mock_server_status, query_server

api_router = APIRouter(prefix="/api", tags=["API"])
repo = ServerRepository()


@api_router.get("/suggestions", response_model=List[Dict[str, Any]])
async def get_suggestions(
    q: str = Query("", description="Search query string"),
    limit: int = Query(5, ge=1, le=20, description="Max suggestions to return"),
):
    """Return autocomplete server suggestions matching query."""
    return search_suggestions(q, limit=limit)


@api_router.get("/status/{address}", response_model=ServerStatus)
async def get_server_status(
    address: str,
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    mock: bool = Query(False, description="Return mock data"),
):
    """Query live server status and update telemetry history."""
    clean_addr = resolve_address(address.strip())
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=bedrock)

    # Persist telemetry for tracking
    server_id = await repo.get_or_create_server(
        address=clean_addr, edition="bedrock" if bedrock else "java"
    )
    await repo.record_telemetry(server_id, status)
    return status


@api_router.get("/history/{address}", response_model=List[TelemetryPoint])
async def get_server_history(
    address: str,
    hours: int = Query(24, ge=1, le=168, description="History window in hours"),
):
    """Retrieve time-series telemetry points for graphing."""
    clean_addr = resolve_address(address.strip())
    server_id = await repo.get_or_create_server(clean_addr)
    history = await repo.get_24h_history(server_id, hours=hours)
    return history


@api_router.get("/badge/{filename}")
async def get_badge(
    filename: str,
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    label: Optional[str] = Query(None, description="Custom label for badge"),
    show_ping: bool = Query(True, description="Include latency in badge"),
    mock: bool = Query(False, description="Return mock data for badge"),
):
    """Generate dynamic SVG badge styled like Shields.io. Filename can end with .svg."""
    raw_addr = filename[:-4] if filename.endswith(".svg") else filename
    clean_addr = resolve_address(raw_addr.strip())
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=bedrock)

    config = BadgeConfig(
        label=label or clean_addr.split(":")[0],
        show_ping=show_ping,
    )
    svg_content = generate_status_badge(status, config)

    return Response(
        content=svg_content,
        media_type="image/svg+xml",
        headers={
            "Cache-Control": "public, max-age=60, s-maxage=60",
            "Content-Disposition": "inline",
        },
    )
