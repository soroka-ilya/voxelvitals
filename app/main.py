"""FastAPI main application entrypoint for VoxelVitals."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.api_routes import api_router
from app.api.routes import web_router
from app.config import settings
from app.database import init_db
from app.repository import ServerRepository
from app.services.pinger import query_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("voxelvitals")

repo = ServerRepository()


async def background_telemetry_poller():
    """Periodic worker that polls tracked servers and prunes old telemetry."""
    logger.info("Background telemetry poller started.")
    while True:
        try:
            # Seed featured servers into DB if not present
            for addr in settings.featured_servers:
                await repo.get_or_create_server(addr, is_pinned=True)

            servers = await repo.get_all_servers()
            for s in servers:
                addr = s["address"]
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
    description="Production-grade Minecraft server telemetry and analytics engine.",
    version="1.0.0",
    lifespan=lifespan,
)

# Static files directory
static_dir = Path(__file__).resolve().parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Mount Routers
app.include_router(web_router)
app.include_router(api_router)
