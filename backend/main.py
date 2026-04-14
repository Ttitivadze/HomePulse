import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware

from backend.integrations.proxmox import router as proxmox_router, fetch_all_proxmox_data
from backend.integrations.docker_int import router as docker_router, fetch_all_docker_data
from backend.integrations.arr import (
    router as arr_router,
    fetch_radarr_data,
    fetch_sonarr_data,
    fetch_lidarr_data,
    fetch_streaming_data,
)
from backend.integrations.claude_chat import router as claude_router
from backend.integrations.uptime_kuma import router as uptime_kuma_router, fetch_uptime_kuma_data
from backend.integrations.infrastructure import router as infra_router, fetch_infrastructure_data
from backend.integrations.self_stats import router as self_stats_router, fetch_self_stats_data
from backend.integrations.bookmarks import (
    public_router as bookmarks_public_router,
    admin_router as bookmarks_admin_router,
    _fetch_bookmarks as fetch_bookmarks_data,
)
from backend.integrations.settings import router as settings_router
from backend.notifications import router as notifications_router
from backend.integrations.api_keys import router as api_keys_router, require_api_key_or_jwt
from backend.auth import router as auth_router
from backend.config import settings

logger = logging.getLogger("homepulse")

_version_file = Path(__file__).parent.parent / "VERSION"
__version__ = _version_file.read_text().strip() if _version_file.is_file() else "2.0.0"


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
    if settings.CLAUDE_API_KEY:
        configured.append("Claude")
    if settings.UPTIME_KUMA_URL:
        configured.append("Uptime Kuma")
    if settings.TELEGRAM_BOT_TOKEN:
        configured.append("Telegram Notifications")

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

    # Shutdown: close shared httpx clients and database
    from backend.integrations import arr, proxmox
    from backend import database as db_mod

    if arr._client is not None and not arr._client.is_closed:
        await arr._client.aclose()
    if proxmox._client is not None and not proxmox._client.is_closed:
        await proxmox._client.aclose()
    await db_mod.close_db()
    logger.info("HomePulse stopped")


app = FastAPI(title="HomePulse", version=__version__, lifespan=lifespan)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Cache static assets (version query param busts cache on redeploy)
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# CORS policy:
#   - Default (DASHBOARD_REQUIRE_AUTH=false): allow any origin so the
#     dashboard works from any device on the LAN without configuration.
#   - With auth on: restrict to the configured ALLOWED_ORIGINS list so
#     credentialed requests (JWT / X-API-Key) can't be issued from
#     untrusted origins. An empty list means same-origin only.
if settings.DASHBOARD_REQUIRE_AUTH:
    cors_origins = settings.ALLOWED_ORIGINS or []
    logger.info(
        "CORS locked to %s (DASHBOARD_REQUIRE_AUTH=true)",
        cors_origins or "same-origin only",
    )
else:
    cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    allow_credentials=False,
)

# API routes
app.include_router(proxmox_router, prefix="/api/proxmox", tags=["proxmox"])
app.include_router(docker_router, prefix="/api/docker", tags=["docker"])
app.include_router(arr_router, prefix="/api/arr", tags=["arr"])
app.include_router(claude_router, prefix="/api/claude", tags=["claude"])
app.include_router(uptime_kuma_router, prefix="/api/uptime-kuma", tags=["uptime-kuma"])
app.include_router(infra_router, prefix="/api/infrastructure", tags=["infrastructure"])
app.include_router(self_stats_router, prefix="/api/self-stats", tags=["self-stats"])
app.include_router(bookmarks_public_router, prefix="/api/bookmarks", tags=["bookmarks"])
app.include_router(bookmarks_admin_router, prefix="/api/settings/bookmarks", tags=["bookmarks"])
app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(settings_router, prefix="/api/settings", tags=["settings"])
app.include_router(notifications_router, prefix="/api/notifications", tags=["notifications"])
app.include_router(api_keys_router, prefix="/api/settings/api-keys", tags=["api-keys"])


# Conditional auth gate for /api/dashboard and per-section read endpoints.
# When DASHBOARD_REQUIRE_AUTH=true, require either a JWT or X-API-Key;
# otherwise pass through anonymously (v1.x backward-compatible default).
async def optional_dashboard_auth(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    authorization: str | None = Header(default=None),
):
    if not settings.DASHBOARD_REQUIRE_AUTH:
        return None
    # Delegate to the real auth check. We re-dispatch manually so the flag
    # short-circuit doesn't force Depends() wiring into every endpoint.
    from fastapi.security import HTTPAuthorizationCredentials
    creds = None
    if authorization and authorization.lower().startswith("bearer "):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization[7:])
    return await require_api_key_or_jwt(request=request, x_api_key=x_api_key, creds=creds)

# Static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Read index.html template once at startup; version placeholder replaced per-request
_index_template = (static_dir / "index.html").read_text()


@app.get("/")
async def root():
    html = _index_template.replace("__APP_VERSION__", __version__)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/dashboard")
async def dashboard(_principal: dict | None = Depends(optional_dashboard_auth)):
    """Fetch all dashboard sections concurrently in a single request."""
    results = await asyncio.gather(
        fetch_all_proxmox_data(),
        fetch_all_docker_data(),
        fetch_radarr_data(),
        fetch_sonarr_data(),
        fetch_lidarr_data(),
        fetch_streaming_data(),
        fetch_uptime_kuma_data(),
        fetch_infrastructure_data(),
        fetch_self_stats_data(),
        fetch_bookmarks_data(),
        return_exceptions=True,
    )

    def safe(result):
        if isinstance(result, Exception):
            logger.error("Dashboard section failed: %s", result)
            return {"configured": False, "error": "Service unavailable"}
        return result

    (proxmox, docker, radarr, sonarr, lidarr, streaming,
     uptime_kuma, infrastructure, self_stats, bookmarks) = results

    # Bookmarks return a raw list from the DB — wrap in the standard
    # envelope so the frontend treats it like any other section.
    if isinstance(bookmarks, Exception):
        logger.error("Bookmarks fetch failed: %s", bookmarks)
        bookmarks_section = {"configured": False, "error": "Bookmarks unavailable", "items": []}
    else:
        bookmarks_section = {"configured": bool(bookmarks), "error": None, "items": bookmarks}

    return {
        "proxmox": safe(proxmox),
        "docker": safe(docker),
        "radarr": safe(radarr),
        "sonarr": safe(sonarr),
        "lidarr": safe(lidarr),
        "streaming": safe(streaming),
        "uptime_kuma": safe(uptime_kuma),
        "infrastructure": safe(infrastructure),
        "self_stats": safe(self_stats),
        "bookmarks": bookmarks_section,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
