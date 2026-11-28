"""FastAPI main application entrypoint for VoxelVitals."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
import urllib.parse
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from app.api.api_routes import api_router
from app.api.routes import web_router
from app.config import settings
from app.database import init_db
from app.limiter import limiter
from app.repository import ServerRepository
from app.services.i18n_service import (
    LANGUAGE_METADATA,
    SUPPORTED_LANGUAGES,
    get_request_language,
    set_current_lang,
    t,
)
from app.services.pinger import is_safe_address, query_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voxelvitals")

repo = ServerRepository()


async def background_telemetry_poller():
    """Periodic worker that polls tracked servers and prunes old telemetry."""
    try:
        import fcntl
    except ImportError:
        fcntl = None

    lock_fh = None
    if fcntl is not None:
        lock_path = Path(f"{settings.db_path}.poller.lock")
        lock_fh = open(lock_path, "a+")
        try:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            lock_fh.close()
            logger.info("Background telemetry poller handled by another worker; skipping.")
            return

    logger.info("Background telemetry poller started.")
    try:
        while True:
            try:
                # Seed featured servers into DB if not present
                for addr in settings.featured_servers:
                    await repo.get_or_create_server(addr, is_pinned=True)

                servers = await repo.get_all_servers()
                for s in servers:
                    addr = s["address"]
                    if not is_safe_address(addr) and not s.get("is_pinned"):
                        continue
                    is_bedrock = s["edition"] == "bedrock"
                    status = await query_server(addr, is_bedrock=is_bedrock)
                    await repo.record_telemetry(s["id"], status)

                # Prune records older than 24h
                pruned = await repo.prune_old_telemetry(hours=settings.history_retention_hours)
                if pruned > 0:
                    logger.debug(f"Pruned {pruned} outdated telemetry entries.")
            except asyncio.CancelledError:
                logger.info("Background poller cancelled.")
                break
            except Exception as exc:
                logger.error(f"Error during poller cycle: {exc}")

            await asyncio.sleep(settings.poll_interval_seconds)
    finally:
        if lock_fh is not None:
            try:
                lock_fh.close()
            except Exception:
                pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing DB setup and background worker."""
    await init_db()
    # Initialize featured servers
    for addr in settings.featured_servers:
        await repo.get_or_create_server(addr, is_pinned=True)

    poller_task = asyncio.create_task(background_telemetry_poller())
    try:
        yield
    finally:
        poller_task.cancel()
        try:
            await poller_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    description="Stateless Minecraft server monitoring and telemetry engine.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.enable_docs else None,
    redoc_url="/redoc" if settings.enable_docs else None,
    openapi_url="/openapi.json" if settings.enable_docs else None,
)

def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Слишком много запросов. Пожалуйста, повторите попытку позже.",
        },
        headers={"Retry-After": "60"},
    )


app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, custom_rate_limit_handler)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Enforce strict security headers across all HTTP responses."""
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def _is_safe_redirect(url: str) -> bool:
    """Validate internal redirect to prevent open redirect vulnerabilities."""
    if not url or not isinstance(url, str):
        return False
    if url.startswith("//") or url.startswith("/\\") or "\\" in url:
        return False
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme or parsed.netloc:
        return False
    return url.startswith("/")


def _normalize_same_origin_referer(referer: Optional[str], request: Request) -> str:
    """Extract safe relative path from same-origin Referer header."""
    if not referer or not isinstance(referer, str):
        return "/"
    cleaned = referer.strip()
    if cleaned.startswith("//") or cleaned.startswith("/\\") or "\\" in cleaned:
        return "/"
    parsed = urllib.parse.urlsplit(cleaned)
    if parsed.scheme or parsed.netloc:
        req_host = (request.headers.get("host") or request.url.netloc or "").split(":")[0].lower()
        ref_host = (parsed.hostname or "").lower()
        if not req_host or ref_host != req_host:
            return "/"
        path = parsed.path or "/"
        rel = f"{path}?{parsed.query}" if parsed.query else path
        return rel if _is_safe_redirect(rel) else "/"
    return cleaned if _is_safe_redirect(cleaned) else "/"


@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    """Resolve request language and populate ContextVar / request state."""
    lang = get_request_language(request)
    set_current_lang(lang)
    request.state.lang = lang
    response = await call_next(request)

    # If explicit ?lang= was requested, persist to cookie
    query_lang = request.query_params.get("lang")
    if query_lang and query_lang.lower() in SUPPORTED_LANGUAGES:
        response.set_cookie(
            key="vv_lang",
            value=query_lang.lower(),
            max_age=365 * 86400,
            httponly=False,
            samesite="lax",
            path="/",
        )
    return response


@app.get("/set-lang/{code}")
@app.post("/api/lang/{code}")
async def set_language_endpoint(
    code: str,
    request: Request,
    redirect: Optional[str] = None,
):
    """Switch user language, persist in vv_lang cookie, and redirect back."""
    target_lang = code.lower() if code.lower() in SUPPORTED_LANGUAGES else "ru"
    if redirect:
        ref = redirect if _is_safe_redirect(redirect) else "/"
    else:
        ref = _normalize_same_origin_referer(request.headers.get("referer"), request)
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url=ref, status_code=303)
    resp.set_cookie(
        key="vv_lang",
        value=target_lang,
        max_age=365 * 86400,
        httponly=False,
        samesite="lax",
        path="/",
    )
    return resp


@app.get("/healthz")
@app.get("/health")
async def healthz_check():
    """Render and Kubernetes root healthcheck endpoint."""
    return {"status": "ok", "version": "1.0.0"}


# Static files directory
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount Routers
app.include_router(web_router)
app.include_router(api_router)
