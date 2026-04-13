import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_dashboard_aggregates_all_sections(async_client):
    """The /api/dashboard endpoint should return all sections with a timestamp."""
    mock_proxmox = {"configured": False, "nodes": []}
    mock_docker = {"configured": False, "containers": []}
    mock_arr = {"configured": False}
    mock_streaming = {"configured": False}

    with (
        patch(
            "backend.main.fetch_proxmox_data",
            new_callable=AsyncMock,
            return_value=mock_proxmox,
        ),
        patch(
            "backend.main.fetch_docker_data",
            new_callable=AsyncMock,
            return_value=mock_docker,
        ),
        patch(
            "backend.main.fetch_radarr_data",
            new_callable=AsyncMock,
            return_value=mock_arr,
        ),
        patch(
            "backend.main.fetch_sonarr_data",
            new_callable=AsyncMock,
            return_value=mock_arr,
        ),
        patch(
            "backend.main.fetch_lidarr_data",
            new_callable=AsyncMock,
            return_value=mock_arr,
        ),
        patch(
            "backend.main.fetch_streaming_data",
            new_callable=AsyncMock,
            return_value=mock_streaming,
        ),
    ):
        async with async_client as client:
            resp = await client.get("/api/dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert "proxmox" in data
    assert "docker" in data
    assert "radarr" in data
    assert "sonarr" in data
    assert "lidarr" in data
    assert "streaming" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_dashboard_handles_exception_gracefully(async_client):
    """If a fetch function raises, the dashboard should still return 200."""
    with (
        patch(
            "backend.main.fetch_proxmox_data",
            new_callable=AsyncMock,
            side_effect=RuntimeError("connection refused"),
        ),
        patch(
            "backend.main.fetch_docker_data",
            new_callable=AsyncMock,
            return_value={"configured": False, "containers": []},
        ),
        patch(
            "backend.main.fetch_radarr_data",
            new_callable=AsyncMock,
            return_value={"configured": False},
        ),
        patch(
            "backend.main.fetch_sonarr_data",
            new_callable=AsyncMock,
            return_value={"configured": False},
        ),
        patch(
            "backend.main.fetch_lidarr_data",
            new_callable=AsyncMock,
            return_value={"configured": False},
        ),
        patch(
            "backend.main.fetch_streaming_data",
            new_callable=AsyncMock,
            return_value={"configured": False},
        ),
    ):
        async with async_client as client:
            resp = await client.get("/api/dashboard")

    assert resp.status_code == 200
    data = resp.json()
    assert data["proxmox"]["error"] == "Service unavailable"
