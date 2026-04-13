import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache

logger = logging.getLogger("homelab.arr")

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
        logger.warning("Cannot connect to Radarr at %s", settings.RADARR_URL)
        return {"configured": True, "error": "Cannot connect to Radarr"}
    except Exception as e:
        logger.exception("Radarr fetch failed")
        return {"configured": True, "error": "Radarr request failed"}


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
        logger.warning("Cannot connect to Sonarr at %s", settings.SONARR_URL)
        return {"configured": True, "error": "Cannot connect to Sonarr"}
    except Exception as e:
        logger.exception("Sonarr fetch failed")
        return {"configured": True, "error": "Sonarr request failed"}


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
        logger.warning("Cannot connect to Lidarr at %s", settings.LIDARR_URL)
        return {"configured": True, "error": "Cannot connect to Lidarr"}
    except Exception as e:
        logger.exception("Lidarr fetch failed")
        return {"configured": True, "error": "Lidarr request failed"}


@router.get("/lidarr")
async def get_lidarr():
    """Get Lidarr music stats and download queue."""
    data = await fetch_lidarr_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Streaming (Jellyfin / Plex / Tautulli) ────────────────────────


async def _fetch_jellyfin_sessions() -> list:
    """Fetch active sessions from Jellyfin's /Sessions endpoint."""
    if not settings.JELLYFIN_URL or not settings.JELLYFIN_API_KEY:
        return []
    client = await _get_client()
    resp = await client.get(
        f"{settings.JELLYFIN_URL}/Sessions",
        headers={"X-Emby-Token": settings.JELLYFIN_API_KEY},
    )
    resp.raise_for_status()
    sessions = []
    for s in resp.json():
        now_playing = s.get("NowPlayingItem")
        if not now_playing:
            continue
        # Build a title like "Show - S01E02 - Episode Name" or just the item name
        title = now_playing.get("Name", "Unknown")
        series = now_playing.get("SeriesName")
        if series:
            ep = now_playing.get("ParentIndexNumber", "")
            ep_num = now_playing.get("IndexNumber", "")
            ep_tag = f"S{ep:02d}E{ep_num:02d}" if ep and ep_num else ""
            title = f"{series} - {ep_tag} - {title}" if ep_tag else f"{series} - {title}"

        play_state = s.get("PlayState", {})
        runtime = now_playing.get("RunTimeTicks", 1) or 1
        position = play_state.get("PositionTicks", 0) or 0
        progress = round(position / runtime * 100, 1)

        sessions.append(
            {
                "user": s.get("UserName", "Unknown"),
                "title": title,
                "media_type": now_playing.get("Type", "unknown").lower(),
                "state": "playing" if not play_state.get("IsPaused") else "paused",
                "progress": progress,
                "quality": now_playing.get("MediaStreams", [{}])[0].get("DisplayTitle", "")
                if now_playing.get("MediaStreams")
                else "",
                "player": s.get("Client", ""),
                "transcode": (
                    "transcode"
                    if s.get("TranscodingInfo")
                    else "direct play"
                ),
                "source": "Jellyfin",
            }
        )
    return sessions


async def _fetch_plex_sessions() -> list:
    """Fetch active sessions from Plex's /status/sessions endpoint."""
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        return []
    client = await _get_client()
    resp = await client.get(
        f"{settings.PLEX_URL}/status/sessions",
        headers={
            "X-Plex-Token": settings.PLEX_TOKEN,
            "Accept": "application/json",
        },
    )
    resp.raise_for_status()
    container = resp.json().get("MediaContainer", {})
    sessions = []
    for item in container.get("Metadata", []):
        title = item.get("title", "Unknown")
        grandparent = item.get("grandparentTitle", "")
        if grandparent:
            season = item.get("parentIndex", "")
            episode = item.get("index", "")
            ep_tag = f"S{int(season):02d}E{int(episode):02d}" if season and episode else ""
            title = f"{grandparent} - {ep_tag} - {title}" if ep_tag else f"{grandparent} - {title}"

        duration = int(item.get("duration", 1)) or 1
        view_offset = int(item.get("viewOffset", 0))
        progress = round(view_offset / duration * 100, 1)

        transcode = "direct play"
        if item.get("TranscodeSession"):
            transcode = "transcode"
        elif item.get("Media"):
            parts = item["Media"][0].get("Part", [{}])
            decision = parts[0].get("decision", "") if parts else ""
            if decision == "transcode":
                transcode = "transcode"

        sessions.append(
            {
                "user": item.get("User", {}).get("title", "Unknown"),
                "title": title,
                "media_type": item.get("type", "unknown"),
                "state": item.get("Player", {}).get("state", "unknown"),
                "progress": progress,
                "quality": item.get("Media", [{}])[0].get("videoResolution", "")
                if item.get("Media")
                else "",
                "player": item.get("Player", {}).get("product", ""),
                "transcode": transcode,
                "source": "Plex",
            }
        )
    return sessions


async def _fetch_tautulli_sessions() -> list:
    """Fetch active sessions from Tautulli's get_activity endpoint."""
    data = await _fetch_tautulli("get_activity")
    if data is None:
        return []
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
                "source": "Tautulli",
            }
        )
    return sessions


async def fetch_streaming_data() -> dict:
    """Fetch streaming sessions from all configured sources (Jellyfin, Plex, Tautulli)."""
    has_jellyfin = bool(settings.JELLYFIN_URL and settings.JELLYFIN_API_KEY)
    has_plex = bool(settings.PLEX_URL and settings.PLEX_TOKEN)
    has_tautulli = bool(settings.TAUTULLI_URL and settings.TAUTULLI_API_KEY)

    if not has_jellyfin and not has_plex and not has_tautulli:
        return {"configured": False}

    cached = cache.get("streaming")
    if cached is not None:
        return cached

    # Fetch from all configured sources concurrently
    tasks = []
    labels = []
    if has_jellyfin:
        tasks.append(_fetch_jellyfin_sessions())
        labels.append("Jellyfin")
    if has_plex:
        tasks.append(_fetch_plex_sessions())
        labels.append("Plex")
    if has_tautulli:
        tasks.append(_fetch_tautulli_sessions())
        labels.append("Tautulli")

    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.exception("Streaming fetch failed")
        return {"configured": True, "error": "Streaming request failed"}

    sessions = []
    errors = []
    for label, res in zip(labels, results):
        if isinstance(res, Exception):
            logger.warning("Streaming source %s failed: %s", label, res)
            errors.append(f"{label}: {res}")
        else:
            sessions.extend(res)

    if not sessions and errors:
        return {"configured": True, "error": "; ".join(errors)}

    result = {
        "configured": True,
        "stream_count": len(sessions),
        "sessions": sessions,
        "sources": labels,
    }
    cache.put("streaming", result)
    return result


@router.get("/streaming")
async def get_streaming():
    """Get current streaming activity from Jellyfin, Plex, and/or Tautulli."""
    data = await fetch_streaming_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data
