from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.integrations.proxmox import router as proxmox_router
from backend.integrations.docker_int import router as docker_router
from backend.integrations.arr import router as arr_router
from backend.integrations.openclaw import router as openclaw_router

app = FastAPI(title="HomeLab Dashboard", version="1.0.0")

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
