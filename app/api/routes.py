"""Web frontend page routes and HTMX partials."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.repository import ServerRepository
from app.services.pinger import get_mock_server_status, query_server

templates_path = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

web_router = APIRouter(tags=["Web Pages"])
repo = ServerRepository()


@web_router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Render home landing page with search bar and featured servers."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "featured_servers": settings.featured_servers,
            "app_name": settings.app_name,
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
    clean_addr = address.strip()
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    await repo.record_telemetry(server_id, status)
    history = await repo.get_24h_history(server_id, hours=24)

    return templates.TemplateResponse(
        request=request,
        name="server.html",
        context={
            "status": status,
            "history": history,
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
    clean_addr = address.strip()
    if mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    await repo.record_telemetry(server_id, status)

    return templates.TemplateResponse(
        request=request,
        name="partials/server_card.html",
        context={"status": status},
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
