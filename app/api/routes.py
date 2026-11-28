"""Web frontend page routes and HTMX partials."""

from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.config import settings
from app.repository import ServerRepository
from app.services.alias_service import (
    check_search_route,
    get_catalog_page,
    get_curated_catalog,
    get_server_extra_info,
    is_bedrock_address,
    resolve_address,
    search_servers_catalog,
)
from app.services.pinger import get_mock_server_status, query_server
from app.services.probes_service import get_multi_region_probes
from app.services.i18n_service import (
    LANGUAGE_METADATA,
    SUPPORTED_LANGUAGES,
    get_request_language,
    t,
)

templates_path = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

# Wire Jinja2 i18n helper globals
templates.env.globals["t"] = t
templates.env.globals["_"] = t
templates.env.globals["SUPPORTED_LANGUAGES"] = SUPPORTED_LANGUAGES
templates.env.globals["LANGUAGE_METADATA"] = LANGUAGE_METADATA
templates.env.globals["get_lang"] = get_request_language
templates.env.globals["is_docs_enabled"] = lambda: settings.enable_docs

web_router = APIRouter(tags=["Web Pages"])
repo = ServerRepository()


@web_router.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Redirect default favicon request to static vector icon."""
    return RedirectResponse(url="/static/favicon.svg")


@web_router.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    """Render home landing page with search bar and featured servers."""
    lang = get_request_language(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "featured_servers": settings.featured_servers,
            "app_name": settings.app_name,
            "catalog": get_curated_catalog(lang=lang),
            "current_lang": lang,
        },
    )


@web_router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query("", description="Search query string"),
    address: str = Query("", description="Alternative address query parameter"),
    bedrock: bool = Query(False),
    category: Optional[str] = Query(None),
    edition: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
):
    """Smart search route: redirects on exact match, or renders dedicated results page."""
    raw_query = q.strip() or address.strip()
    if not raw_query:
        return RedirectResponse(url="/", status_code=303)

    route_type, target = check_search_route(raw_query, bedrock=bedrock)

    if route_type == "direct":
        effective_bedrock = bedrock or is_bedrock_address(target)
        url = f"/server/{target}"
        if effective_bedrock:
            url += "?bedrock=true"
        return RedirectResponse(url=url, status_code=303)

    # Partial / Multi-match query -> Render dedicated search results page
    lang = get_request_language(request)
    eff_edition = "bedrock" if bedrock else (edition or "all")
    results = search_servers_catalog(raw_query, category=category, edition=eff_edition, lang=lang)
    page_items, total_pages, total_count = get_catalog_page(
        page=page,
        page_size=6,
        servers=results,
    )
    resolved_fallback = resolve_address(raw_query)

    return templates.TemplateResponse(
        request=request,
        name="search.html",
        context={
            "query": raw_query,
            "results": page_items,
            "total_count": total_count,
            "total_pages": total_pages,
            "current_page": page,
            "bedrock": bedrock,
            "category": category or "all",
            "edition": eff_edition,
            "resolved_fallback": resolved_fallback,
            "app_name": settings.app_name,
            "current_lang": lang,
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
    effective_mock = mock and settings.enable_mock_auth
    if effective_mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    if server_id > 0:
        await repo.record_telemetry(server_id, status)
    history = await repo.get_24h_history(server_id, hours=24)

    lang = get_request_language(request)
    extra_info = get_server_extra_info(clean_addr, edition=status.edition)
    probes = get_multi_region_probes(
        clean_addr,
        status.latency_ms,
        edition=status.edition,
        is_online=status.is_online,
        lang=lang,
    )
    peak_info = await repo.get_server_peak(clean_addr)

    return templates.TemplateResponse(
        request=request,
        name="server.html",
        context={
            "status": status,
            "history": history,
            "extra_info": extra_info,
            "probes": probes,
            "peak_info": peak_info,
            "app_name": settings.app_name,
            "current_lang": lang,
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
    effective_mock = mock and settings.enable_mock_auth
    if effective_mock:
        status = get_mock_server_status(clean_addr, is_online=True, edition="bedrock" if effective_bedrock else "java")
    else:
        status = await query_server(clean_addr, is_bedrock=effective_bedrock)

    server_id = await repo.get_or_create_server(clean_addr, edition=status.edition)
    if server_id > 0:
        await repo.record_telemetry(server_id, status)
    extra_info = get_server_extra_info(clean_addr, edition=status.edition)
    lang = get_request_language(request)

    return templates.TemplateResponse(
        request=request,
        name="partials/server_card.html",
        context={"status": status, "extra_info": extra_info, "current_lang": lang},
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
    lang = get_request_language(request)
    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={"app_name": settings.app_name, "current_lang": lang},
    )


@web_router.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms of Service page adhering to anti-vibecoding guidelines."""
    lang = get_request_language(request)
    return templates.TemplateResponse(
        request=request,
        name="terms.html",
        context={"app_name": settings.app_name, "current_lang": lang},
    )
