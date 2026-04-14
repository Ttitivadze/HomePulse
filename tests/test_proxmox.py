import pytest
from unittest.mock import patch, AsyncMock

from backend.integrations.proxmox import fetch_proxmox_data


@pytest.mark.asyncio
async def test_proxmox_not_configured():
    with patch("backend.integrations.proxmox.settings") as mock_settings:
        mock_settings.PROXMOX_HOST = ""
        result = await fetch_proxmox_data()
    assert result == {"configured": False, "nodes": []}


@pytest.mark.asyncio
async def test_proxmox_endpoint_returns_data(async_client):
    mock_data = {
        "configured": True,
        "instances": [{"name": "Default", "configured": True, "nodes": [], "url": "https://test:8006"}],
    }
    with patch(
        "backend.integrations.proxmox.fetch_all_proxmox_data",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        async with async_client as client:
            resp = await client.get("/api/proxmox/status")
    assert resp.status_code == 200
    assert resp.json() == mock_data


@pytest.mark.asyncio
async def test_proxmox_endpoint_returns_503_on_error(async_client):
    mock_data = {
        "configured": True,
        "instances": [{"name": "Default", "configured": True, "nodes": [], "error": "Cannot connect"}],
    }
    with patch(
        "backend.integrations.proxmox.fetch_all_proxmox_data",
        new_callable=AsyncMock,
        return_value=mock_data,
    ):
        async with async_client as client:
            resp = await client.get("/api/proxmox/status")
    assert resp.status_code == 503
