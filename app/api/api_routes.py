"""REST JSON API and dynamic SVG badge endpoints."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from app.domain.models import BadgeConfig, ServerStatus, TelemetryPoint
from app.repository import ServerRepository
from app.services.alias_service import is_bedrock_address, resolve_address, search_suggestions
from app.services.auth_service import (
    generate_session_token,
    get_current_user_from_request,
    hash_password,
    verify_password,
)
from app.services.badge_service import generate_status_badge
from app.services.pinger import get_mock_server_status, query_server

api_router = APIRouter(prefix="/api", tags=["API"])
repo = ServerRepository()


@api_router.get("/health")
async def health_check():
    """Service health and database readiness check for Docker / Cloud orchestrators."""
    try:
        await repo.get_all_servers()
        db_status = "connected"
    except Exception as exc:
        db_status = f"unhealthy: {exc}"
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
    metadata: Optional[str] = None


@api_router.post("/analytics/event")
async def track_event(request: Request, payload: AnalyticsEventRequest):
    """Record interactive client-side telemetry event."""
    vid = getattr(request.state, "visitor_id", None) or request.cookies.get("vv_vid") or "unknown"
    await repo.record_event(
        visitor_id=vid,
        event_type=payload.event_type,
        target=payload.target,
        metadata=payload.metadata,
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
    bedrock: bool = Query(False, description="Query Bedrock edition"),
    mock: bool = Query(False, description="Return mock data"),
):
    """Query live server status and update telemetry history."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock)

    # Persist telemetry for tracking
    server_id = await repo.get_or_create_server(
        address=clean_addr, edition="bedrock" if effective_bedrock else "java"
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


# ----------------- Auth Endpoints -----------------
@api_router.post("/auth/register", status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, response: Response):
    """Register a new user account."""
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
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 86400,
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "mc_nickname": user["mc_nickname"],
        "role": user["role"],
    }


@api_router.post("/auth/login")
async def login(payload: LoginRequest, response: Response):
    """Authenticate user and issue session cookie."""
    user = await repo.get_user_by_username(payload.username)
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Неверное имя пользователя или пароль")

    token = generate_session_token()
    await repo.create_session(token, user["id"])
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        samesite="lax",
        max_age=30 * 86400,
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "mc_nickname": user["mc_nickname"],
        "role": user["role"],
    }


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


@api_router.post("/reviews")
async def create_review(payload: ReviewCreateRequest, request: Request):
    """Submit a rating and review for a server."""
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
async def create_news(payload: NewsCreateRequest, request: Request):
    """Publish a news article for a server."""
    clean_addr = resolve_address(payload.server_address.strip())
    user = await get_current_user_from_request(request, repo)
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
@api_router.post("/vote")
async def vote_server(request: Request, payload: Dict[str, str]):
    """Cast a daily vote for a server."""
    raw_addr = payload.get("server_address", "")
    if not raw_addr:
        raise HTTPException(status_code=400, detail="Укажите адрес сервера")
    clean_addr = resolve_address(raw_addr.strip())

    # Hash client IP for privacy & rate limiting
    client_ip = request.client.host if request.client else "127.0.0.1"
    import hashlib
    ip_hash = hashlib.sha256(client_ip.encode("utf-8")).hexdigest()

    success = await repo.vote_server(clean_addr, ip_hash)
    total_votes = await repo.get_votes_count(clean_addr)
    if not success:
        return {"success": False, "message": "Вы уже голосовали за этот сервер сегодня!", "votes": total_votes}
    return {"success": True, "message": "Спасибо за ваш голос!", "votes": total_votes}


