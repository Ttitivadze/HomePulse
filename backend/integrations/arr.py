import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache
from backend.integrations._status import ok, failure, unconfigured

logger = logging.getLogger("homepulse.arr")

router = APIRouter()

# Module-level shared client; created lazily, closed during app shutdown.
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


async def _api_get(
    url: str,
    *,
    api_key: str | None = None,
    headers: dict | None = None,
    params: dict | None = None,
    key_header: str = "X-Api-Key",
    response_path: tuple[str, ...] = (),
):
    """Shared GET helper for arr / Tautulli / anything using the module httpx client.

    - When ``api_key`` is given and ``params`` doesn't already carry it, the key
      goes in the configured ``key_header`` header (Radarr/Sonarr/Lidarr style).
    - ``response_path`` walks into the parsed JSON (e.g. Tautulli returns
      ``{"response": {"data": ...}}`` and wants ``("response", "data")``).
    - Returns ``None`` if the url is empty — keeps callers terse.
    """
    if not url:
        return None
    client = await _get_client()
    req_headers = dict(headers or {})
    if api_key and not (params and "apikey" in params):
        req_headers[key_header] = api_key
    resp = await client.get(url, headers=req_headers, params=params)
    resp.raise_for_status()
    data = resp.json()
    for key in response_path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


async def _fetch(base_url: str, api_key: str, endpoint: str) -> dict | list | None:
    """Radarr / Sonarr / Lidarr API v3 helper."""
    if not base_url or not api_key:
        return None
    return await _api_get(f"{base_url}/api/v3/{endpoint}", api_key=api_key)


async def _fetch_tautulli(cmd: str) -> dict | None:
    """Tautulli API v2 helper — key goes in the query string, not a header."""
    if not settings.TAUTULLI_URL or not settings.TAUTULLI_API_KEY:
        return None
    return await _api_get(
        f"{settings.TAUTULLI_URL}/api/v2",
        params={"apikey": settings.TAUTULLI_API_KEY, "cmd": cmd},
        response_path=("response", "data"),
    )


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
        return unconfigured()

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

        data = ok(
            total=total,
            downloaded=downloaded,
            missing=total - downloaded,
            requested=monitored_missing,
            unmonitored=unmonitored_missing,
            queue=_build_queue_items(queue),
        )
        cache.put("radarr", data)
        return data
    except httpx.ConnectError:
        logger.warning("Cannot connect to Radarr at %s", settings.RADARR_URL)
        return failure("Cannot connect to Radarr")
    except Exception:
        logger.exception("Radarr fetch failed")
        return failure("Radarr request failed")


@router.get("/radarr")
async def get_radarr():
    """Get Radarr movie stats and download queue."""
    data = await fetch_radarr_data()
    if data.get("error"):
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Sonarr ──────────────────────────────────────────────────────────


async def fetch_sonarr_data() -> dict:
    if not settings.SONARR_URL:
        return unconfigured()

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

        data = ok(
            total_shows=total_shows,
            monitored_shows=monitored_shows,
            total_episodes=total_episodes,
            missing_episodes=missing_episodes,
            queue=_build_queue_items(queue),
        )
        cache.put("sonarr", data)
        return data
    except httpx.ConnectError:
        logger.warning("Cannot connect to Sonarr at %s", settings.SONARR_URL)
        return failure("Cannot connect to Sonarr")
    except Exception:
        logger.exception("Sonarr fetch failed")
        return failure("Sonarr request failed")


@router.get("/sonarr")
async def get_sonarr():
    """Get Sonarr TV show stats and download queue."""
    data = await fetch_sonarr_data()
    if data.get("error"):
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Lidarr ──────────────────────────────────────────────────────────


async def fetch_lidarr_data() -> dict:
    if not settings.LIDARR_URL:
        return unconfigured()

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

        data = ok(
            total_artists=total_artists,
            monitored_artists=monitored_artists,
            total_albums=total_albums,
            queue=_build_queue_items(queue),
        )
        cache.put("lidarr", data)
        return data
    except httpx.ConnectError:
        logger.warning("Cannot connect to Lidarr at %s", settings.LIDARR_URL)
        return failure("Cannot connect to Lidarr")
    except Exception:
        logger.exception("Lidarr fetch failed")
        return failure("Lidarr request failed")


@router.get("/lidarr")
async def get_lidarr():
    """Get Lidarr music stats and download queue."""
    data = await fetch_lidarr_data()
    if data.get("error"):
        raise HTTPException(status_code=503, detail=data["error"])
    return data


# ── Streaming (Jellyfin / Plex / Tautulli) ────────────────────────

# Shape of a single normalized streaming session. Each *_sessions fetcher
# returns a list of dicts with exactly these keys so the frontend only
# has one schema to render. Centralising the schema here means adding a
# new field in the future (e.g. bitrate) is a single-line change.
_SESSION_FIELDS = (
    "source", "user", "title", "media_type", "state",
    "progress", "quality", "player", "transcode",
)


def _session(source: str, **kwargs) -> dict:
    """Build a streaming-session dict with defensive defaults.

    Any field not provided is filled with a sensible default ("Unknown"
    for identifying fields, "" for optional ones). Extra kwargs are
    silently ignored so source-specific key typos surface in tests, not
    in production.
    """
    defaults = {
        "source": source,
        "user": "Unknown",
        "title": "Unknown",
        "media_type": "unknown",
        "state": "unknown",
        "progress": 0,
        "quality": "",
        "player": "",
        "transcode": "direct play",
    }
    for key in _SESSION_FIELDS:
        if key in kwargs and kwargs[key] is not None:
            defaults[key] = kwargs[key]
    if isinstance(defaults["media_type"], str):
        defaults["media_type"] = defaults["media_type"].lower()
    return defaults


def _episode_title(series: str | None, season_idx, episode_idx, item_title: str | None) -> str:
    """Build "Show - S01E02 - Episode" when series info is available, else fall back.

    Shared between Jellyfin and Plex because both have the same show/season/
    episode shape even though the field names differ.
    """
    item_title = item_title or "Unknown"
    if not series:
        return item_title
    try:
        tag = f"S{int(season_idx):02d}E{int(episode_idx):02d}"
    except (TypeError, ValueError):
        return f"{series} - {item_title}"
    return f"{series} - {tag} - {item_title}"


def _progress_pct(position, total) -> float:
    """Percent-complete helper; returns 0 when total is missing / zero.

    Note: the pre-refactor code used `total or 1` as a guard which quietly
    inflated progress to >100% for missing-duration items. We return 0
    here since "unknown progress" is a more honest signal than a
    nonsense number.
    """
    try:
        total_int = int(total) if total is not None else 0
        position_int = int(position or 0)
    except (TypeError, ValueError):
        return 0
    if total_int <= 0:
        return 0
    return round(position_int / total_int * 100, 1)


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

        play_state = s.get("PlayState", {})
        media_streams = now_playing.get("MediaStreams") or [{}]

        sessions.append(_session(
            "Jellyfin",
            user=s.get("UserName"),
            title=_episode_title(
                now_playing.get("SeriesName"),
                now_playing.get("ParentIndexNumber"),
                now_playing.get("IndexNumber"),
                now_playing.get("Name"),
            ),
            media_type=now_playing.get("Type"),
            state="paused" if play_state.get("IsPaused") else "playing",
            progress=_progress_pct(play_state.get("PositionTicks"), now_playing.get("RunTimeTicks")),
            quality=media_streams[0].get("DisplayTitle", ""),
            player=s.get("Client"),
            transcode="transcode" if s.get("TranscodingInfo") else "direct play",
        ))
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
        media = item.get("Media") or []

        transcode = "direct play"
        if item.get("TranscodeSession"):
            transcode = "transcode"
        elif media:
            parts = media[0].get("Part") or []
            if parts and parts[0].get("decision") == "transcode":
                transcode = "transcode"

        sessions.append(_session(
            "Plex",
            user=item.get("User", {}).get("title"),
            title=_episode_title(
                item.get("grandparentTitle"),
                item.get("parentIndex"),
                item.get("index"),
                item.get("title"),
            ),
            media_type=item.get("type"),
            state=item.get("Player", {}).get("state"),
            progress=_progress_pct(item.get("viewOffset"), item.get("duration")),
            quality=media[0].get("videoResolution", "") if media else "",
            player=item.get("Player", {}).get("product"),
            transcode=transcode,
        ))
    return sessions


async def _fetch_tautulli_sessions() -> list:
    """Fetch active sessions from Tautulli's get_activity endpoint."""
    data = await _fetch_tautulli("get_activity")
    if data is None:
        return []
    return [
        _session(
            "Tautulli",
            user=s.get("friendly_name"),
            title=s.get("full_title") or s.get("title"),
            media_type=s.get("media_type"),
            state=s.get("state"),
            progress=s.get("progress_percent", 0),
            quality=s.get("quality_profile", ""),
            player=s.get("player"),
            transcode=s.get("transcode_decision", "direct play"),
        )
        for s in data.get("sessions", [])
    ]


async def fetch_streaming_data() -> dict:
    """Fetch streaming sessions from all configured sources (Jellyfin, Plex, Tautulli)."""
    has_jellyfin = bool(settings.JELLYFIN_URL and settings.JELLYFIN_API_KEY)
    has_plex = bool(settings.PLEX_URL and settings.PLEX_TOKEN)
    has_tautulli = bool(settings.TAUTULLI_URL and settings.TAUTULLI_API_KEY)

    if not has_jellyfin and not has_plex and not has_tautulli:
        return unconfigured()

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
    except Exception:
        logger.exception("Streaming fetch failed")
        return failure("Streaming request failed")

    sessions = []
    errors = []
    for label, res in zip(labels, results):
        if isinstance(res, Exception):
            logger.warning("Streaming source %s failed: %s", label, res)
            errors.append(label)
        else:
            sessions.extend(res)

    if not sessions and errors:
        return failure(f"Cannot connect to {', '.join(errors)}")

    result = ok(
        stream_count=len(sessions),
        sessions=sessions,
        sources=labels,
    )
    cache.put("streaming", result)
    return result


@router.get("/streaming")
async def get_streaming():
    """Get current streaming activity from Jellyfin, Plex, and/or Tautulli."""
    data = await fetch_streaming_data()
    if data.get("error"):
        raise HTTPException(status_code=503, detail=data["error"])
    return data
