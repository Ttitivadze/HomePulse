import pytest
from unittest.mock import patch, AsyncMock

from backend.integrations.docker_int import fetch_docker_data


@pytest.mark.asyncio
async def test_docker_not_configured():
    with patch("backend.integrations.docker_int._get_client", return_value=None):
        result = await fetch_docker_data()
    assert result == {"configured": False, "containers": []}


@pytest.mark.asyncio
async def test_docker_endpoint_returns_data(async_client):
    mock_data = {"configured": True, "containers": []}
    with patch(
        "backend.integrations.docker_int.fetch_docker_data",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        async with async_client as client:
            resp = await client.get("/api/docker/containers")
    assert resp.status_code == 200
    assert resp.json() == mock_data
