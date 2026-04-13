import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

from backend.integrations.proxmox import router as proxmox_router, fetch_proxmox_data
from backend.integrations.docker_int import router as docker_router, fetch_docker_data
from backend.integrations.arr import (
    router as arr_router,
    fetch_radarr_data,
    fetch_sonarr_data,
    fetch_lidarr_data,
    fetch_streaming_data,
)
from backend.integrations.openclaw import router as openclaw_router
from backend.integrations.settings import router as settings_router
from backend.auth import router as auth_router
from backend.config import settings

logger = logging.getLogger("homepulse")

_version_file = Path(__file__).parent.parent / "VERSION"
__version__ = _version_file.read_text().strip() if _version_file.is_file() else "1.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    from backend.config import settings

    configured = []
    if settings.PROXMOX_HOST:
        configured.append("Proxmox")
    if settings.RADARR_URL:
        configured.append("Radarr")
    if settings.SONARR_URL:
        configured.append("Sonarr")
    if settings.JELLYFIN_URL:
        configured.append("Jellyfin")
    if settings.PLEX_URL:
        configured.append("Plex")
    if settings.TAUTULLI_URL:
        configured.append("Tautulli")
    if settings.OPENCLAW_URL:
        configured.append("OpenClaw")

    # Initialize the database
    from backend import database as db
    await db.init_db()

    logger.info(
        f"HomePulse v{__version__} starting — configured services: %s",
        ", ".join(configured) if configured else "(none)",
    )
    if settings.warnings:
        for w in settings.warnings:
            logger.warning(w)

    yield

    # Shutdown: close the shared httpx client used by arr + openclaw
    from backend.integrations import arr

    if arr._client is not None and not arr._client.is_closed:
        await arr._client.aclose()
    logger.info("HomePulse stopped")


app = FastAPI(title="HomePulse", version=__version__, lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS — allow any origin so the dashboard works from any device on the LAN
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# API routes
app.include_router(proxmox_router, prefix="/api/proxmox", tags=["proxmox"])
app.include_router(docker_router, prefix="/api/docker", tags=["docker"])
app.include_router(arr_router, prefix="/api/arr", tags=["arr"])
app.include_router(openclaw_router, prefix="/api/openclaw", tags=["openclaw"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(static_dir / "index.html"))


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
async def dashboard():
    """Fetch all dashboard sections concurrently in a single request."""
    results = await asyncio.gather(
        fetch_proxmox_data(),
        fetch_docker_data(),
        fetch_radarr_data(),
        fetch_sonarr_data(),
        fetch_lidarr_data(),
        fetch_streaming_data(),
        return_exceptions=True,
    )

    def safe(result):
        if isinstance(result, Exception):
            logger.error("Dashboard section failed: %s", result)
            return {"configured": False, "error": "Service unavailable"}
        return result

    proxmox, docker, radarr, sonarr, lidarr, streaming = results

    return {
        "proxmox": safe(proxmox),
        "docker": safe(docker),
        "radarr": safe(radarr),
        "sonarr": safe(sonarr),
        "lidarr": safe(lidarr),
        "streaming": safe(streaming),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
