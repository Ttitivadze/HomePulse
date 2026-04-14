"""Uptime Kuma integration — monitor status dashboard widget."""

import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache

logger = logging.getLogger("homepulse.uptime_kuma")

router = APIRouter()


async def fetch_uptime_kuma_data() -> dict:
    """Fetch Uptime Kuma status. Returns a dict; never raises."""
    if not settings.UPTIME_KUMA_URL:
        return {"configured": False}

    cached = cache.get("uptime_kuma", ttl=30)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(f"{settings.UPTIME_KUMA_URL}/api/entry-page")
            if resp.status_code == 200:
                data = {
                    "configured": True,
                    "status": "online",
                    "url": settings.UPTIME_KUMA_URL,
                }
            else:
                data = {
                    "configured": True,
                    "status": "degraded",
                    "url": settings.UPTIME_KUMA_URL,
                }
    except httpx.ConnectError:
        data = {"configured": True, "status": "offline", "url": settings.UPTIME_KUMA_URL}
    except Exception:
        logger.exception("Uptime Kuma fetch failed")
        data = {"configured": True, "status": "error", "url": settings.UPTIME_KUMA_URL}

    cache.put("uptime_kuma", data)
    return data


@router.get("/status")
async def get_uptime_kuma_status():
    data = await fetch_uptime_kuma_data()
    if not data.get("configured"):
        return data
    if data.get("status") == "offline":
        raise HTTPException(status_code=503, detail="Uptime Kuma is offline")
    return data
