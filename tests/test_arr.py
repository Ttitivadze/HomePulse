import pytest
from unittest.mock import patch, AsyncMock

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
        result = await fetch_streaming_data()
    assert result == {"configured": False}


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
