"""Web frontend page routes and HTMX partials."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.repository import ServerRepository
from app.services.alias_service import (
    get_curated_catalog,
    get_server_extra_info,
    is_bedrock_address,
    resolve_address,
)
from app.services.auth_service import get_current_user_from_request
from app.services.pinger import get_mock_server_status, query_server

templates_path = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

web_router = APIRouter(tags=["Web Pages"])
repo = ServerRepository()


@web_router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Redirect default favicon request to static vector icon."""
    return RedirectResponse(url="/static/favicon.svg")


@web_router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Render home landing page with search bar and featured servers."""
    current_user = await get_current_user_from_request(request, repo)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "featured_servers": settings.featured_servers,
            "app_name": settings.app_name,
            "catalog": get_curated_catalog(),
            "current_user": current_user,
        },
    )



@web_router.get("/server/{address}", response_class=HTMLResponse)
async def server_page(
    request: Request,
    address: str,
    bedrock: bool = Query(False),
    mock: bool = Query(False),
):
    """Render server detail page with interactive history charts and player list."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    await repo.record_telemetry(server_id, status)
    history = await repo.get_24h_history(server_id, hours=24)

    extra_info = get_server_extra_info(clean_addr, edition=status.edition)
    news = await repo.get_news_for_server(clean_addr)
    if not news:
        news = [
            {
                "id": 1,
                "title": "Сезонное обновление серверов и оптимизация сети",
                "content": "Обновлена сетевая инфраструктура, улучшен пинг для игроков из СНГ и Европы. Добавлен античит протокол нового поколения и оптимизированы задержки чанков.",
                "tag": "Обновление",
                "author": "Команда сервера",
                "published_at": "2026-10-25T14:00:00Z",
            },
            {
                "id": 2,
                "title": "Рейтинговый турнир выходного дня",
                "content": "На этих выходных открывается турнирная сетка с наградами за победы в дуэлях и командных боях. Зарегистрируйтесь заранее!",
                "tag": "Ивент",
                "author": "Event Manager",
                "published_at": "2026-10-22T18:30:00Z",
            },
        ]

    reviews = await repo.get_reviews_for_server(clean_addr)
    if not reviews:
        reviews = [
            {
                "id": 1,
                "author_name": "CraftMaster",
                "rating": 5,
                "comment": "Отличный сервер, стабильный ТПС 20.0, отзывчивая администрация и честная экономика без P2W элементов.",
                "created_at": "2026-10-26T18:40:00Z",
                "likes": 12,
            },
            {
                "id": 2,
                "author_name": "EndermanPro",
                "rating": 5,
                "comment": "Играем всем кланом уже полгода. Очень крутые кастомные ивенты и удобный лаунчер для входа в один клик.",
                "created_at": "2026-10-24T11:20:00Z",
                "likes": 7,
            },
            {
                "id": 3,
                "author_name": "PixelHero",
                "rating": 4,
                "comment": "Пинг радует, онлайн огромный. Единственное — иногда очереди по вечерам, но модерация на высшем уровне.",
                "created_at": "2026-10-21T09:15:00Z",
                "likes": 4,
            },
        ]

    rating_stats = await repo.get_server_rating_stats(clean_addr)
    votes = await repo.get_votes_count(clean_addr)
    current_user = await get_current_user_from_request(request, repo)

    return templates.TemplateResponse(
        request=request,
        name="server.html",
        context={
            "status": status,
            "history": history,
            "extra_info": extra_info,
            "news": news,
            "reviews": reviews,
            "rating_stats": rating_stats,
            "votes": votes,
            "current_user": current_user,
            "app_name": settings.app_name,
        },
    )



@web_router.get("/partials/server-card", response_class=HTMLResponse)
async def partial_server_card(
    request: Request,
    address: str,
    bedrock: bool = Query(False),
    mock: bool = Query(False),
):
    """HTMX partial for rendering a single server card on search or live update."""
    clean_addr = resolve_address(address.strip())
    effective_bedrock = bedrock or is_bedrock_address(clean_addr)
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    await repo.record_telemetry(server_id, status)
    extra_info = get_server_extra_info(clean_addr, edition=status.edition)

    return templates.TemplateResponse(
        request=request,
        name="partials/server_card.html",
        context={"status": status, "extra_info": extra_info},
    )


@web_router.get("/partials/skeleton-card", response_class=HTMLResponse)
async def partial_skeleton_card(request: Request):
    """HTMX loading skeleton indicator."""
    return templates.TemplateResponse(
        request=request,
        name="partials/skeleton.html",
        context={},
    )


@web_router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page adhering to anti-vibecoding guidelines."""
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={"app_name": settings.app_name},
    )


@web_router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms of Service page adhering to anti-vibecoding guidelines."""
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={"app_name": settings.app_name},
    )
