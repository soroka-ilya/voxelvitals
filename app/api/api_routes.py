"""REST JSON API and dynamic SVG badge endpoints."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from app.config import settings
from app.domain.models import BadgeConfig, ServerStatus, TelemetryPoint
from app.limiter import get_real_client_ip, limiter
from app.repository import ServerRepository
from app.services.alias_service import is_bedrock_address, resolve_address, search_suggestions
from app.services.auth_service import (
    generate_session_token,
    get_current_user_from_request,
    hash_password,
    is_legacy_hash,
    verify_password,
)
from app.services.badge_service import generate_status_badge
from app.services.pinger import get_mock_server_status, is_safe_address, query_server
from app.services.probes_service import get_multi_region_probes
from app.services.rate_limiter import review_rate_limiter, vote_rate_limiter

api_router = APIRouter(prefix="/api", tags=["API"])
repo = ServerRepository()


def _is_request_https(request: Request) -> bool:
    """Detect if connection is encrypted either directly or through reverse proxy."""
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


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


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=30)
    password: str = Field(..., min_length=6)
    mc_nickname: Optional[str] = ""
    email: Optional[str] = ""


class LoginRequest(BaseModel):
    username: str
    password: str


class ReviewCreateRequest(BaseModel):
    server_address: str
    rating: int = Field(..., ge=1, le=5)
    comment: str = Field(..., min_length=3, max_length=1000)
    author_name: Optional[str] = None


class NewsCreateRequest(BaseModel):
    server_address: str
    title: str = Field(..., min_length=3, max_length=120)
    content: str = Field(..., min_length=5, max_length=5000)
    tag: str = "Обновление"
    author: Optional[str] = "Администрация"


class AnalyticsEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=50)
    target: Optional[str] = None
    metadata: Optional[Union[Dict[str, Any], str]] = None


@api_router.post("/analytics/event")
async def track_event(request: Request, payload: AnalyticsEventRequest):
    """Record interactive client-side telemetry event."""
    vid = getattr(request.state, "visitor_id", None) or request.cookies.get("vv_vid") or "unknown"
    meta_str = (
        json.dumps(payload.metadata, ensure_ascii=False)
        if isinstance(payload.metadata, dict)
        else payload.metadata
    )
    await repo.record_event(
        visitor_id=vid,
        event_type=payload.event_type,
        target=payload.target,
        metadata=meta_str,
    )
    return {"status": "ok"}



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
    request: Request,
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    mock: bool = Query(False, description="Return mock data"),
    force_refresh: bool = Query(False, description="Bypass cache and force refresh"),
):
    """Query live server status and update telemetry history."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    if mock:
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
    safe_interval = max(interval, 3)

    async def event_generator():
        while True:
            try:
                if mock:
                    status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
                else:
                    status = await query_server(clean_addr, is_bedrock=effective_bedrock)
                probes = get_multi_region_probes(clean_addr, status.latency_ms, edition=status.edition, is_online=status.is_online)
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


# ----------------- Auth Endpoints -----------------
@api_router.post("/auth/register", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def register(payload: RegisterRequest, request: Request, response: Response):
    """Register a new user account with scrypt password hashing."""
    existing = await repo.get_user_by_username(payload.username)
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким логином уже существует")

    pwd_hash = hash_password(payload.password)
    user_id = await repo.create_user(
        username=payload.username,
        password_hash=pwd_hash,
        mc_nickname=payload.mc_nickname or payload.username,
        email=payload.email or "",
    )
    user = await repo.get_user_by_id(user_id)
    token = generate_session_token()
    await repo.create_session(token, user_id)
    is_secure = _is_request_https(request)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=30 * 86400,
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "mc_nickname": user["mc_nickname"],
        "role": user["role"],
    }


@api_router.post("/auth/login")
@limiter.limit("10/minute")
async def login(payload: LoginRequest, request: Request, response: Response):
    """Authenticate user, auto-upgrade legacy hash to scrypt, and issue session cookie."""
    user = await repo.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    # Transparent auto-upgrade legacy SHA-256 hash to scrypt
    if is_legacy_hash(user["password_hash"]):
        try:
            await repo.update_user_password(user["id"], hash_password(payload.password))
        except Exception:
            pass

    token = generate_session_token()
    await repo.create_session(token, user["id"])
    is_secure = _is_request_https(request)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        max_age=30 * 86400,
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "mc_nickname": user["mc_nickname"],
        "role": user["role"],
    }


@api_router.post("/auth/logout")
@api_router.get("/auth/logout")
async def logout(request: Request, response: Response):
    """Log out user and clear session cookie."""
    token = request.cookies.get("session_token")
    if token:
        await repo.delete_session(token)
    response.delete_cookie("session_token")
    return {"message": "Успешный выход из системы"}


@api_router.get("/auth/me")
async def get_me(request: Request):
    """Get currently authenticated user info."""
    user = await get_current_user_from_request(request, repo)
    if not user:
        raise HTTPException(status_code=401, detail="Не авторизован")
    return {
        "id": user["id"],
        "username": user["username"],
        "mc_nickname": user["mc_nickname"],
        "role": user["role"],
    }


# ----------------- Reviews Endpoints -----------------
@api_router.get("/reviews")
async def get_reviews(address: str = Query(..., description="Server address")):
    """Get reviews and aggregate rating stats for a server."""
    clean_addr = resolve_address(address.strip())
    reviews = await repo.get_reviews_for_server(clean_addr)
    return reviews


@api_router.get("/reviews/{address}")
async def get_reviews_by_path(address: str):
    """Get reviews for a server by path parameter."""
    clean_addr = resolve_address(address.strip())
    return await repo.get_reviews_for_server(clean_addr)


@api_router.post("/reviews", dependencies=[Depends(review_rate_limiter)])
@limiter.limit("5/minute")
async def create_review(request: Request, payload: ReviewCreateRequest):
    """Submit a rating and review for a server (rate limited to 5 req/min)."""
    clean_addr = resolve_address(payload.server_address.strip())
    user = await get_current_user_from_request(request, repo)
    author_name = payload.author_name or (user["mc_nickname"] if user else "Анонимный игрок")
    user_id = user["id"] if user else None

    review_id = await repo.add_review(
        server_address=clean_addr,
        author_name=author_name,
        rating=payload.rating,
        comment=payload.comment,
        user_id=user_id,
    )
    return {
        "id": review_id,
        "server_address": clean_addr,
        "author_name": author_name,
        "rating": payload.rating,
        "comment": payload.comment,
    }


# ----------------- News Endpoints -----------------
@api_router.get("/news")
async def get_news(address: str = Query(..., description="Server address")):
    """Get news updates for a server."""
    clean_addr = resolve_address(address.strip())
    news = await repo.get_news_for_server(clean_addr)
    return news


@api_router.post("/news")
@limiter.limit("5/minute")
async def create_news(payload: NewsCreateRequest, request: Request):
    """Publish a news article for a server. Protected by admin role check and rate limiting."""
    clean_addr = resolve_address(payload.server_address.strip())
    user = await get_current_user_from_request(request, repo)

    if settings.require_news_admin:
        admin_header = request.headers.get("X-Admin-Key")
        is_key_valid = bool(settings.admin_api_key and admin_header == settings.admin_api_key)
        is_admin_user = bool(user and user.get("role") == "admin")
        if not (is_key_valid or is_admin_user):
            if not user:
                raise HTTPException(status_code=401, detail="Необходима авторизация")
            raise HTTPException(status_code=403, detail="Требуются права администратора")

    author = payload.author or (user["username"] if user else "Администрация")

    news_id = await repo.add_news(
        server_address=clean_addr,
        title=payload.title,
        content=payload.content,
        tag=payload.tag,
        author=author,
    )
    return {
        "id": news_id,
        "server_address": clean_addr,
        "title": payload.title,
        "content": payload.content,
        "tag": payload.tag,
        "author": author,
    }


# ----------------- Vote Endpoint -----------------
@api_router.post("/vote", dependencies=[Depends(vote_rate_limiter)])
async def vote_server(request: Request, payload: Dict[str, str]):
    """Cast a daily vote for a server (rate limited to 10 req/min)."""
    raw_addr = payload.get("server_address", "")
    if not raw_addr:
        raise HTTPException(status_code=400, detail="Укажите адрес сервера")
    clean_addr = resolve_address(raw_addr.strip())

    # Hash real client IP for privacy & rate limiting
    client_ip = get_real_client_ip(request)
    import hashlib
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()

    success = await repo.vote_server(clean_addr, ip_hash)
    total_votes = await repo.get_votes_count(clean_addr)
    if not success:
        return {"success": False, "message": "Вы уже голосовали за этот сервер сегодня!", "votes": total_votes}
    return {"success": True, "message": "Спасибо за ваш голос!", "votes": total_votes}


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


