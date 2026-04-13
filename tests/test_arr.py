import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from backend.integrations.arr import (
    fetch_radarr_data,
    fetch_sonarr_data,
    fetch_lidarr_data,
    fetch_streaming_data,
)


@pytest.mark.asyncio
async def test_radarr_not_configured():
    with patch("backend.integrations.arr.settings") as mock_settings:
        mock_settings.RADARR_URL = ""
        mock_settings.RADARR_API_KEY = ""
        result = await fetch_radarr_data()
    assert result == {"configured": False}


@pytest.mark.asyncio
async def test_radarr_returns_stats_and_requested():
    movies = [
        {"hasFile": True, "monitored": True},
        {"hasFile": True, "monitored": True},
        {"hasFile": False, "monitored": True},   # requested
        {"hasFile": False, "monitored": False},   # unmonitored
    ]
    queue = {"records": []}

    async def mock_fetch(base_url, api_key, endpoint):
        if endpoint == "movie":
            return movies
        return queue

    with (
        patch("backend.integrations.arr.settings") as mock_settings,
        patch("backend.integrations.arr._fetch", side_effect=mock_fetch),
    ):
        mock_settings.RADARR_URL = "http://radarr:7878"
        mock_settings.RADARR_API_KEY = "key"
        result = await fetch_radarr_data()

    assert result["configured"] is True
    assert result["total"] == 4
    assert result["downloaded"] == 2
    assert result["requested"] == 1
    assert result["unmonitored"] == 1
    assert result["missing"] == 2


@pytest.mark.asyncio
async def test_sonarr_not_configured():
    with patch("backend.integrations.arr.settings") as mock_settings:
        mock_settings.SONARR_URL = ""
        mock_settings.SONARR_API_KEY = ""
        result = await fetch_sonarr_data()
    assert result == {"configured": False}


@pytest.mark.asyncio
async def test_lidarr_not_configured():
    with patch("backend.integrations.arr.settings") as mock_settings:
        mock_settings.LIDARR_URL = ""
        mock_settings.LIDARR_API_KEY = ""
        result = await fetch_lidarr_data()
    assert result == {"configured": False}


@pytest.mark.asyncio
async def test_streaming_not_configured():
    with patch("backend.integrations.arr.settings") as mock_settings:
        mock_settings.TAUTULLI_URL = ""
        mock_settings.TAUTULLI_API_KEY = ""
        mock_settings.JELLYFIN_URL = ""
        mock_settings.JELLYFIN_API_KEY = ""
        mock_settings.PLEX_URL = ""
        mock_settings.PLEX_TOKEN = ""
        result = await fetch_streaming_data()
    assert result == {"configured": False}


@pytest.mark.asyncio
async def test_streaming_jellyfin_sessions():
    """Jellyfin sessions should be parsed into normalized session objects."""
    from backend.integrations.arr import _fetch_jellyfin_sessions

    jellyfin_resp = [
        {
            "UserName": "Alice",
            "Client": "Jellyfin Web",
            "NowPlayingItem": {
                "Name": "Pilot",
                "SeriesName": "Breaking Bad",
                "ParentIndexNumber": 1,
                "IndexNumber": 1,
                "Type": "Episode",
                "RunTimeTicks": 36000000000,
                "MediaStreams": [{"DisplayTitle": "1080p"}],
            },
            "PlayState": {"PositionTicks": 18000000000, "IsPaused": False},
            "TranscodingInfo": None,
        },
        {
            "UserName": "Bob",
            "Client": "Jellyfin Android",
            "PlayState": {},
            # No NowPlayingItem → should be skipped
        },
    ]

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = jellyfin_resp
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with (
        patch("backend.integrations.arr.settings") as mock_settings,
        patch("backend.integrations.arr._get_client", return_value=mock_client),
    ):
        mock_settings.JELLYFIN_URL = "http://jellyfin:8096"
        mock_settings.JELLYFIN_API_KEY = "key"
        sessions = await _fetch_jellyfin_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s["user"] == "Alice"
    assert "Breaking Bad" in s["title"]
    assert "S01E01" in s["title"]
    assert s["source"] == "Jellyfin"
    assert s["state"] == "playing"
    assert s["progress"] == 50.0


@pytest.mark.asyncio
async def test_streaming_plex_sessions():
    """Plex direct sessions should be parsed into normalized session objects."""
    from backend.integrations.arr import _fetch_plex_sessions

    plex_resp = {
        "MediaContainer": {
            "Metadata": [
                {
                    "title": "Ozymandias",
                    "grandparentTitle": "Breaking Bad",
                    "parentIndex": 5,
                    "index": 14,
                    "type": "episode",
                    "duration": 60000,
                    "viewOffset": 30000,
                    "User": {"title": "Charlie"},
                    "Player": {"product": "Plex Web", "state": "playing"},
                    "Media": [{"videoResolution": "1080", "Part": [{"decision": "directplay"}]}],
                },
            ]
        }
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = plex_resp
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    with (
        patch("backend.integrations.arr.settings") as mock_settings,
        patch("backend.integrations.arr._get_client", return_value=mock_client),
    ):
        mock_settings.PLEX_URL = "http://plex:32400"
        mock_settings.PLEX_TOKEN = "token"
        sessions = await _fetch_plex_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s["user"] == "Charlie"
    assert "Breaking Bad" in s["title"]
    assert "S05E14" in s["title"]
    assert s["source"] == "Plex"
    assert s["progress"] == 50.0
    assert s["transcode"] == "direct play"


@pytest.mark.asyncio
async def test_streaming_merges_multiple_sources():
    """fetch_streaming_data should merge sessions from all configured sources."""
    with (
        patch("backend.integrations.arr.settings") as mock_settings,
        patch(
            "backend.integrations.arr._fetch_jellyfin_sessions",
            new_callable=AsyncMock,
            return_value=[{"user": "A", "source": "Jellyfin", "title": "Movie A"}],
        ),
        patch(
            "backend.integrations.arr._fetch_tautulli_sessions",
            new_callable=AsyncMock,
            return_value=[{"user": "B", "source": "Tautulli", "title": "Movie B"}],
        ),
    ):
        mock_settings.JELLYFIN_URL = "http://jellyfin:8096"
        mock_settings.JELLYFIN_API_KEY = "key"
        mock_settings.PLEX_URL = ""
        mock_settings.PLEX_TOKEN = ""
        mock_settings.TAUTULLI_URL = "http://tautulli:8181"
        mock_settings.TAUTULLI_API_KEY = "key"
        result = await fetch_streaming_data()

    assert result["configured"] is True
    assert result["stream_count"] == 2
    assert result["sessions"][0]["source"] == "Jellyfin"
    assert result["sessions"][1]["source"] == "Tautulli"


@pytest.mark.asyncio
async def test_radarr_endpoint_returns_503_on_error(async_client):
    """The /api/arr/radarr endpoint should return 503 when Radarr is unreachable."""
    with patch(
        "backend.integrations.arr.fetch_radarr_data",
        new_callable=AsyncMock,
        return_value={"configured": True, "error": "Cannot connect to Radarr"},
    ):
        async with async_client as client:
            resp = await client.get("/api/arr/radarr")
    assert resp.status_code == 503
