import asyncio
import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache

router = APIRouter()

# Module-level shared client; created lazily, closed during app shutdown.
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def _fetch(base_url: str, api_key: str, endpoint: str) -> dict | list | None:
    if not base_url or not api_key:
        return None
    client = await _get_client()
    resp = await client.get(
        f"{base_url}/api/v3/{endpoint}",
        headers={"X-Api-Key": api_key},
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_tautulli(cmd: str) -> dict | None:
    if not settings.TAUTULLI_URL or not settings.TAUTULLI_API_KEY:
        return None
    client = await _get_client()
    resp = await client.get(
        f"{settings.TAUTULLI_URL}/api/v2",
        params={"apikey": settings.TAUTULLI_API_KEY, "cmd": cmd},
    )
    resp.raise_for_status()
    return resp.json().get("response", {}).get("data")


def _build_queue_items(queue_data) -> list:
    items = []
    for item in (queue_data or {}).get("records", []):
        items.append(
            {
                "title": item.get("title", "Unknown"),
                "series": item.get("series", {}).get("title", ""),
                "artist": item.get("artist", {}).get("artistName", ""),
                "status": item.get("status", "unknown"),
                "size": item.get("size", 0),
                "sizeleft": item.get("sizeleft", 0),
                "progress": round(
                    (1 - item.get("sizeleft", 0) / max(item.get("size", 1), 1))
                    * 100,
                    1,
                ),
                "eta": item.get("timeleft"),
            }
        )
    return items


# ── Radarr ──────────────────────────────────────────────────────────


async def fetch_radarr_data() -> dict:
    if not settings.RADARR_URL:
        return {"configured": False}

    cached = cache.get("radarr")
    if cached is not None:
        return cached

    try:
        movies, queue = await asyncio.gather(
            _fetch(settings.RADARR_URL, settings.RADARR_API_KEY, "movie"),
            _fetch(settings.RADARR_URL, settings.RADARR_API_KEY, "queue"),
        )

        total = len(movies) if movies else 0
        downloaded = sum(1 for m in (movies or []) if m.get("hasFile"))
        monitored_missing = sum(
            1 for m in (movies or []) if not m.get("hasFile") and m.get("monitored")
        )
        unmonitored_missing = total - downloaded - monitored_missing

        data = {
            "configured": True,
            "total": total,
            "downloaded": downloaded,
            "missing": total - downloaded,
            "requested": monitored_missing,
            "unmonitored": unmonitored_missing,
            "queue": _build_queue_items(queue),
        }
        cache.put("radarr", data)
        return data
    except httpx.ConnectError:
        return {"configured": True, "error": "Cannot connect to Radarr"}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/radarr")
async def get_radarr():
    """Get Radarr movie stats and download queue."""
    data = await fetch_radarr_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Sonarr ──────────────────────────────────────────────────────────


async def fetch_sonarr_data() -> dict:
    if not settings.SONARR_URL:
        return {"configured": False}

    cached = cache.get("sonarr")
    if cached is not None:
        return cached

    try:
        series, queue = await asyncio.gather(
            _fetch(settings.SONARR_URL, settings.SONARR_API_KEY, "series"),
            _fetch(settings.SONARR_URL, settings.SONARR_API_KEY, "queue"),
        )

        total_shows = len(series) if series else 0
        monitored_shows = sum(1 for s in (series or []) if s.get("monitored"))
        total_episodes = sum(s.get("episodeFileCount", 0) for s in (series or []))
        missing_episodes = sum(
            s.get("episodeCount", 0) - s.get("episodeFileCount", 0)
            for s in (series or [])
        )

        data = {
            "configured": True,
            "total_shows": total_shows,
            "monitored_shows": monitored_shows,
            "total_episodes": total_episodes,
            "missing_episodes": missing_episodes,
            "queue": _build_queue_items(queue),
        }
        cache.put("sonarr", data)
        return data
    except httpx.ConnectError:
        return {"configured": True, "error": "Cannot connect to Sonarr"}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/sonarr")
async def get_sonarr():
    """Get Sonarr TV show stats and download queue."""
    data = await fetch_sonarr_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Lidarr ──────────────────────────────────────────────────────────


async def fetch_lidarr_data() -> dict:
    if not settings.LIDARR_URL:
        return {"configured": False}

    cached = cache.get("lidarr")
    if cached is not None:
        return cached

    try:
        artists, queue = await asyncio.gather(
            _fetch(settings.LIDARR_URL, settings.LIDARR_API_KEY, "artist"),
            _fetch(settings.LIDARR_URL, settings.LIDARR_API_KEY, "queue"),
        )

        total_artists = len(artists) if artists else 0
        monitored_artists = sum(1 for a in (artists or []) if a.get("monitored"))
        total_albums = sum(a.get("albumCount", 0) for a in (artists or []))

        data = {
            "configured": True,
            "total_artists": total_artists,
            "monitored_artists": monitored_artists,
            "total_albums": total_albums,
            "queue": _build_queue_items(queue),
        }
        cache.put("lidarr", data)
        return data
    except httpx.ConnectError:
        return {"configured": True, "error": "Cannot connect to Lidarr"}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/lidarr")
async def get_lidarr():
    """Get Lidarr music stats and download queue."""
    data = await fetch_lidarr_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Streaming (Tautulli) ───────────────────────────────────────────


async def fetch_streaming_data() -> dict:
    if not settings.TAUTULLI_URL:
        return {"configured": False}

    cached = cache.get("streaming")
    if cached is not None:
        return cached

    try:
        data = await _fetch_tautulli("get_activity")
        if data is None:
            return {"configured": False}

        sessions = []
        for s in data.get("sessions", []):
            sessions.append(
                {
                    "user": s.get("friendly_name", "Unknown"),
                    "title": s.get("full_title", s.get("title", "Unknown")),
                    "media_type": s.get("media_type", "unknown"),
                    "state": s.get("state", "unknown"),
                    "progress": s.get("progress_percent", 0),
                    "quality": s.get("quality_profile", ""),
                    "player": s.get("player", ""),
                    "transcode": s.get("transcode_decision", "direct play"),
                    "thumb": s.get("thumb", ""),
                }
            )

        result = {
            "configured": True,
            "stream_count": int(data.get("stream_count", 0)),
            "sessions": sessions,
        }
        cache.put("streaming", result)
        return result
    except httpx.ConnectError:
        return {"configured": True, "error": "Cannot connect to Tautulli"}
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/streaming")
async def get_streaming():
    """Get current Plex streaming activity via Tautulli."""
    data = await fetch_streaming_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data
