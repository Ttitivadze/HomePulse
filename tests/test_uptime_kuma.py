"""Tests for the Uptime Kuma integration."""

import httpx
import pytest

from backend.config import settings
from backend.integrations import uptime_kuma


_METRICS_SAMPLE = """\
# HELP monitor_status Current Status of Monitor
# TYPE monitor_status gauge
monitor_status{monitor_name="Google",monitor_type="http",monitor_url="https://google.com",monitor_hostname="null",monitor_port="null"} 1
monitor_status{monitor_name="Plex",monitor_type="http",monitor_url="https://plex.example.com",monitor_hostname="null",monitor_port="null"} 0
monitor_status{monitor_name="Slow",monitor_type="ping",monitor_url="10.0.0.5",monitor_hostname="10.0.0.5",monitor_port="null"} 2
# HELP monitor_response_time Monitor Response Time (ms)
# TYPE monitor_response_time gauge
monitor_response_time{monitor_name="Google",monitor_type="http",monitor_url="https://google.com",monitor_hostname="null",monitor_port="null"} 76
monitor_response_time{monitor_name="Plex",monitor_type="http",monitor_url="https://plex.example.com",monitor_hostname="null",monitor_port="null"} 0
# HELP monitor_cert_days_remaining Monitor Certificate Days Remaining
# TYPE monitor_cert_days_remaining gauge
monitor_cert_days_remaining{monitor_name="Google",monitor_type="http",monitor_url="https://google.com",monitor_hostname="null",monitor_port="null"} 47
"""


def test_parse_metrics_extracts_monitors():
    result = uptime_kuma._parse_metrics_text(_METRICS_SAMPLE)
    names = [r["name"] for r in result]
    # Urgency ordering: down > pending > up
    assert names == ["Plex", "Slow", "Google"]

    google = next(r for r in result if r["name"] == "Google")
    assert google["status"] == "up"
    assert google["response_time_ms"] == 76
    assert google["cert_days_remaining"] == 47
    assert google["type"] == "http"
    assert google["url"] == "https://google.com"

    plex = next(r for r in result if r["name"] == "Plex")
    assert plex["status"] == "down"
    assert plex["cert_days_remaining"] is None

    slow = next(r for r in result if r["name"] == "Slow")
    assert slow["status"] == "pending"


def test_parse_metrics_empty_text():
    assert uptime_kuma._parse_metrics_text("") == []
    assert uptime_kuma._parse_metrics_text("# just a comment\n") == []


def test_parse_metrics_ignores_unknown_metrics():
    text = 'random_metric{foo="bar"} 1\n'
    assert uptime_kuma._parse_metrics_text(text) == []


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


@pytest.mark.asyncio
async def test_fetch_monitors_disabled_without_token(monkeypatch):
    monkeypatch.setattr(settings, "UPTIME_KUMA_URL", "http://fake:3001")
    monkeypatch.setattr(settings, "UPTIME_KUMA_METRICS_TOKEN", "")
    result = await uptime_kuma._fetch_monitors()
    assert result == []


@pytest.mark.asyncio
async def test_fetch_monitors_parses_metrics(monkeypatch):
    monkeypatch.setattr(settings, "UPTIME_KUMA_URL", "http://fake:3001")
    monkeypatch.setattr(settings, "UPTIME_KUMA_METRICS_TOKEN", "token123")

    async def fake_get(self, url, *args, **kwargs):
        return httpx.Response(200, text=_METRICS_SAMPLE, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    result = await uptime_kuma._fetch_monitors()
    assert len(result) == 3
    assert any(m["name"] == "Google" for m in result)
