"""Tests for the Uptime Kuma integration."""

import httpx
import pytest

from backend.config import settings
from backend.integrations import uptime_kuma


@pytest.mark.asyncio
async def test_uptime_kuma_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "UPTIME_KUMA_URL", "")
    data = await uptime_kuma.fetch_uptime_kuma_data()
    assert data == {"configured": False}


@pytest.mark.asyncio
async def test_uptime_kuma_online(monkeypatch):
    """Direct fetch_uptime_kuma_data unit test — patches httpx which is OK
    because we're not going through the ASGI transport here."""
    monkeypatch.setattr(settings, "UPTIME_KUMA_URL", "http://fake:3001")

    async def fake_get(self, url, *args, **kwargs):
        return httpx.Response(200, text="ok", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    data = await uptime_kuma.fetch_uptime_kuma_data()
    assert data["configured"] is True
    assert data["status"] == "online"
    assert data["url"] == "http://fake:3001"


@pytest.mark.asyncio
async def test_uptime_kuma_offline(monkeypatch):
    monkeypatch.setattr(settings, "UPTIME_KUMA_URL", "http://fake:3001")

    async def fake_get(self, url, *args, **kwargs):
        raise httpx.ConnectError("refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    data = await uptime_kuma.fetch_uptime_kuma_data()
    assert data["configured"] is True
    assert data["status"] == "offline"


@pytest.mark.asyncio
async def test_uptime_kuma_status_endpoint_offline_returns_503(async_client, monkeypatch):
    """Patch fetch_uptime_kuma_data directly — monkeypatching httpx here
    would also break the async_client's own request to the ASGI app."""
    async def fake_fetch():
        return {"configured": True, "status": "offline", "url": "http://fake:3001"}

    monkeypatch.setattr(uptime_kuma, "fetch_uptime_kuma_data", fake_fetch)
    resp = await async_client.get("/api/uptime-kuma/status")
    assert resp.status_code == 503
