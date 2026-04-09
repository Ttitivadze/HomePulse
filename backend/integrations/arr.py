import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings

router = APIRouter()


async def _fetch(base_url: str, api_key: str, endpoint: str) -> dict | list | None:
    if not base_url or not api_key:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{base_url}/api/v3/{endpoint}",
            headers={"X-Api-Key": api_key},
        )
        resp.raise_for_status()
        return resp.json()


async def _fetch_tautulli(cmd: str) -> dict | None:
    if not settings.TAUTULLI_URL or not settings.TAUTULLI_API_KEY:
        return None
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{settings.TAUTULLI_URL}/api/v2",
            params={"apikey": settings.TAUTULLI_API_KEY, "cmd": cmd},
        )
        resp.raise_for_status()
        return resp.json().get("response", {}).get("data")


@router.get("/radarr")
async def get_radarr():
    """Get Radarr movie stats and download queue."""
    if not settings.RADARR_URL:
        return {"configured": False}

    try:
        movies = await _fetch(settings.RADARR_URL, settings.RADARR_API_KEY, "movie")
        queue = await _fetch(settings.RADARR_URL, settings.RADARR_API_KEY, "queue")

        total = len(movies) if movies else 0
        downloaded = sum(1 for m in (movies or []) if m.get("hasFile"))
        missing = total - downloaded

        queue_items = []
        for item in (queue or {}).get("records", []):
            queue_items.append({
                "title": item.get("title", "Unknown"),
                "status": item.get("status", "unknown"),
                "size": item.get("size", 0),
                "sizeleft": item.get("sizeleft", 0),
                "progress": round(
                    (1 - item.get("sizeleft", 0) / max(item.get("size", 1), 1)) * 100, 1
                ),
                "eta": item.get("timeleft"),
            })

        return {
            "configured": True,
            "total": total,
            "downloaded": downloaded,
            "missing": missing,
            "queue": queue_items,
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Radarr")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sonarr")
async def get_sonarr():
    """Get Sonarr TV show stats and download queue."""
    if not settings.SONARR_URL:
        return {"configured": False}

    try:
        series = await _fetch(settings.SONARR_URL, settings.SONARR_API_KEY, "series")
        queue = await _fetch(settings.SONARR_URL, settings.SONARR_API_KEY, "queue")

        total_shows = len(series) if series else 0
        total_episodes = sum(s.get("episodeFileCount", 0) for s in (series or []))
        missing_episodes = sum(
            s.get("episodeCount", 0) - s.get("episodeFileCount", 0)
            for s in (series or [])
        )

        queue_items = []
        for item in (queue or {}).get("records", []):
            queue_items.append({
                "title": item.get("title", "Unknown"),
                "series": item.get("series", {}).get("title", ""),
                "status": item.get("status", "unknown"),
                "size": item.get("size", 0),
                "sizeleft": item.get("sizeleft", 0),
                "progress": round(
                    (1 - item.get("sizeleft", 0) / max(item.get("size", 1), 1)) * 100, 1
                ),
                "eta": item.get("timeleft"),
            })

        return {
            "configured": True,
            "total_shows": total_shows,
            "total_episodes": total_episodes,
            "missing_episodes": missing_episodes,
            "queue": queue_items,
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Sonarr")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lidarr")
async def get_lidarr():
    """Get Lidarr music stats and download queue."""
    if not settings.LIDARR_URL:
        return {"configured": False}

    try:
        artists = await _fetch(settings.LIDARR_URL, settings.LIDARR_API_KEY, "artist")
        queue = await _fetch(settings.LIDARR_URL, settings.LIDARR_API_KEY, "queue")

        total_artists = len(artists) if artists else 0
        total_albums = sum(a.get("albumCount", 0) for a in (artists or []))

        queue_items = []
        for item in (queue or {}).get("records", []):
            queue_items.append({
                "title": item.get("title", "Unknown"),
                "artist": item.get("artist", {}).get("artistName", ""),
                "status": item.get("status", "unknown"),
                "size": item.get("size", 0),
                "sizeleft": item.get("sizeleft", 0),
                "progress": round(
                    (1 - item.get("sizeleft", 0) / max(item.get("size", 1), 1)) * 100, 1
                ),
                "eta": item.get("timeleft"),
            })

        return {
            "configured": True,
            "total_artists": total_artists,
            "total_albums": total_albums,
            "queue": queue_items,
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Lidarr")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/streaming")
async def get_streaming():
    """Get current Plex streaming activity via Tautulli."""
    if not settings.TAUTULLI_URL:
        return {"configured": False}

    try:
        data = await _fetch_tautulli("get_activity")
        if data is None:
            return {"configured": False}

        sessions = []
        for s in data.get("sessions", []):
            sessions.append({
                "user": s.get("friendly_name", "Unknown"),
                "title": s.get("full_title", s.get("title", "Unknown")),
                "media_type": s.get("media_type", "unknown"),
                "state": s.get("state", "unknown"),
                "progress": s.get("progress_percent", 0),
                "quality": s.get("quality_profile", ""),
                "player": s.get("player", ""),
                "transcode": s.get("transcode_decision", "direct play"),
                "thumb": s.get("thumb", ""),
            })

        return {
            "configured": True,
            "stream_count": int(data.get("stream_count", 0)),
            "sessions": sessions,
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Tautulli")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
