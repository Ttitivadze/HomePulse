import pytest
from unittest.mock import patch, AsyncMock

from backend.integrations.docker_int import fetch_docker_data
from backend.config import settings


@pytest.mark.asyncio
async def test_docker_not_configured():
    with patch("backend.integrations.docker_int._get_client", return_value=None):
        result = await fetch_docker_data()
    assert result == {"configured": False, "containers": []}


@pytest.mark.asyncio
async def test_docker_socket_access_error_includes_docker_links(monkeypatch):
    """Regression: error paths must carry docker_links so the frontend
    can still render links even when Docker itself is broken."""
    monkeypatch.setattr(
        settings.__class__,
        "docker_links",
        property(lambda self: {"radarr": "https://example/radarr"}),
    )
    with patch("backend.integrations.docker_int._get_client", return_value=None), \
         patch("backend.integrations.docker_int._check_socket_access", return_value="simulated error"):
        result = await fetch_docker_data()

    assert result["error"] == "simulated error"
    assert result["docker_links"] == {"radarr": "https://example/radarr"}


@pytest.mark.asyncio
async def test_docker_endpoint_returns_data(async_client):
    mock_data = {
        "configured": True,
        "instances": [{"name": "Default", "configured": True, "containers": [], "host_url": ""}],
    }
    with patch(
        "backend.integrations.docker_int.fetch_all_docker_data",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        async with async_client as client:
            resp = await client.get("/api/docker/containers")
    assert resp.status_code == 200
    assert resp.json() == mock_data
