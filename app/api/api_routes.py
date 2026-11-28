"""REST JSON API and dynamic SVG badge endpoints."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.config import settings
from app.domain.models import BadgeConfig, ServerStatus, TelemetryPoint
from app.limiter import limiter
from app.repository import ServerRepository
from app.services.alias_service import is_bedrock_address, resolve_address, search_suggestions
from app.services.badge_service import generate_status_badge
from app.services.i18n_service import get_request_language
from app.services.pinger import get_mock_server_status, is_safe_address, query_server
from app.services.probes_service import get_multi_region_probes

api_router = APIRouter(prefix="/api", tags=["API"])
repo = ServerRepository()


@api_router.get("/health")
async def health_check():
    """Service health and database readiness check for Docker / Cloud orchestrators."""
    try:
        await repo.get_all_servers()
        db_status = "connected"
    except Exception:
        db_status = "degraded"
    return {
        "status": "ok" if db_status == "connected" else "degraded",
        "version": "1.0.0",
        "database": db_status,
    }


@api_router.get("/suggestions", response_model=List[Dict[str, Any]])
async def get_suggestions(
    request: Request,
    q: str = Query("", description="Search query string"),
    limit: int = Query(5, ge=1, le=20, description="Max suggestions to return"),
):
    """Return autocomplete server suggestions matching query."""
    lang = get_request_language(request)
    return search_suggestions(q, limit=limit, lang=lang)


@api_router.get("/status/{address}", response_model=ServerStatus)
async def get_server_status(
    address: str,
    request: Request,
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    mock: bool = Query(False, description="Return mock data"),
    force_refresh: bool = Query(False, description="Bypass cache and force refresh"),
):
    """Query live server status and update telemetry history."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    effective_mock = mock and settings.enable_mock_auth
    if effective_mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock, force_refresh=force_refresh)

    # Persist telemetry for tracking
    server_id = await repo.get_or_create_server(
        address=clean_addr, edition="bedrock" if effective_bedrock else "java"
    )
    if server_id > 0:
        await repo.record_telemetry(server_id, status)
    peak_info = await repo.get_server_peak(clean_addr)
    status.peak_players = peak_info["peak_players"]
    status.peak_online = peak_info["peak_online"]
    status.peak_date = peak_info["peak_date"]
    status.peak_players_time = peak_info.get("peak_players_time")
    status.peak_players_formatted = peak_info.get("formatted")
    return status


@api_router.post("/servers/{address}/ping", response_model=ServerStatus)
@api_router.post("/ping/{address}", response_model=ServerStatus)
@limiter.limit("30/minute")
async def manual_ping_server(
    address: str,
    request: Request,
    bedrock: bool = Query(False),
):
    """Manual ping trigger endpoint rate limited to 30 req/min per IP."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    status = await query_server(clean_addr, is_bedrock=effective_bedrock, force_refresh=True)
    server_id = await repo.get_or_create_server(
        address=clean_addr, edition="bedrock" if effective_bedrock else "java"
    )
    if server_id > 0:
        await repo.record_telemetry(server_id, status)
    peak_info = await repo.get_server_peak(clean_addr)
    status.peak_players = peak_info["peak_players"]
    status.peak_online = peak_info["peak_online"]
    status.peak_date = peak_info["peak_date"]
    status.peak_players_time = peak_info.get("peak_players_time")
    status.peak_players_formatted = peak_info.get("formatted")
    return status


@api_router.get("/sse/status/{address}")
@api_router.get("/live/{address}")
async def live_server_stream(
    address: str,
    request: Request,
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    interval: int = Query(60, ge=1, le=300, description="Stream interval in seconds"),
    mock: bool = Query(False, description="Return mock data"),
):
    """Server-Sent Events (SSE) live telemetry stream.
    Streams real-time player counts, ping, multi-region probes, and peak online.
    """
    clean_addr = resolve_address(address.strip())
    if not is_safe_address(clean_addr):
        raise HTTPException(status_code=400, detail="Недопустимый адрес сервера")

    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    effective_mock = mock and settings.enable_mock_auth
    safe_interval = max(interval, 3)
    lang = get_request_language(request)

    async def event_generator():
        while True:
            try:
                if effective_mock:
                    status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
                else:
                    status = await query_server(clean_addr, is_bedrock=effective_bedrock)
                probes = get_multi_region_probes(
                    clean_addr,
                    status.latency_ms,
                    edition=status.edition,
                    is_online=status.is_online,
                    lang=lang,
                )
                peak_info = await repo.get_server_peak(clean_addr)
                payload = {
                    "address": clean_addr,
                    "is_online": status.is_online,
                    "players_online": status.players_online,
                    "players_max": status.players_max,
                    "latency_ms": status.latency_ms,
                    "region_latencies": status.region_latencies,
                    "peak_players": peak_info["peak_players"],
                    "peak_players_formatted": peak_info.get("formatted"),
                    "version_name": status.version_name,
                    "motd_html": status.motd_html,
                    "probes": [p.to_dict() if hasattr(p, "to_dict") else p for p in probes],
                    "last_updated": status.last_updated,
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                break
            except Exception as exc:
                yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
            try:
                await asyncio.sleep(safe_interval)
            except (asyncio.CancelledError, GeneratorExit):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@api_router.get("/history/{address}", response_model=List[TelemetryPoint])
async def get_server_history(
    address: str,
    hours: int = Query(24, ge=1, le=168, description="History window in hours"),
):
    """Retrieve time-series telemetry points for graphing."""
    clean_addr = resolve_address(address.strip())
    server_id = await repo.get_or_create_server(clean_addr)
    if server_id <= 0:
        return []
    history = await repo.get_24h_history(server_id, hours=hours)
    return history


@api_router.get("/telemetry/{address}", response_model=List[TelemetryPoint])
async def get_server_telemetry(
    address: str,
    hours: int = Query(24, ge=1, le=168, description="History window in hours"),
):
    """Retrieve time-series telemetry points for graphing (alias for /history)."""
    return await get_server_history(address=address, hours=hours)


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
    effective_mock = mock and settings.enable_mock_auth
    if effective_mock:
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


# ----------------- Telegram Bot Webhook Endpoint -----------------
@api_router.post("/tg/webhook")
async def telegram_webhook(request: Request):
    """Receive and process incoming Telegram Bot updates via Webhook.
    Validates X-Telegram-Bot-Api-Secret-Token when secret is configured.
    """
    if settings.telegram_webhook_secret:
        header_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if header_secret != settings.telegram_webhook_secret:
            raise HTTPException(status_code=403, detail="Invalid Telegram secret token")

    from app.services.tg_service import process_telegram_update
    try:
        update_data = await request.json()
    except Exception:
        return {"ok": False, "error": "Invalid JSON"}

    response_payload = await process_telegram_update(update_data)
    if response_payload:
        return response_payload
    return {"ok": True}


