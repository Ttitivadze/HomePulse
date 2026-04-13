import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown: close the shared httpx client used by arr + openclaw
    from backend.integrations import arr

    if arr._client is not None and not arr._client.is_closed:
        await arr._client.aclose()


app = FastAPI(title="HomeLab Dashboard", version="1.0.0", lifespan=lifespan)

# API routes
app.include_router(proxmox_router, prefix="/api/proxmox", tags=["proxmox"])
app.include_router(docker_router, prefix="/api/docker", tags=["docker"])
app.include_router(arr_router, prefix="/api/arr", tags=["arr"])
app.include_router(openclaw_router, prefix="/api/openclaw", tags=["openclaw"])

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
            return {"configured": False, "error": str(result)}
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
