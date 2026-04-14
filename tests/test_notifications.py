"""Tests for the notification framework."""

import httpx
import pytest

from backend.config import settings
from backend import notifications


@pytest.mark.asyncio
async def test_test_endpoint_unconfigured(async_client, monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "")
    resp = await async_client.post("/api/notifications/test")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_send_telegram_success(monkeypatch):
    """Direct unit test of send_telegram — patches httpx so no real request flies."""
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "456")

    captured = {}

    async def fake_post(self, url, *args, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return httpx.Response(200, text="ok", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    ok = await notifications.send_telegram("Hi", "Body", level="success")
    assert ok is True
    assert "token123" in captured["url"]
    assert captured["json"]["chat_id"] == "456"
    assert "Hi" in captured["json"]["text"]


@pytest.mark.asyncio
async def test_send_telegram_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "")
    ok = await notifications.send_telegram("Hi", "Body")
    assert ok is False


@pytest.mark.asyncio
async def test_test_endpoint_success(async_client, monkeypatch):
    """Patch send_notification directly — patching httpx.AsyncClient.post
    would also intercept the test's own request to the FastAPI app."""
    monkeypatch.setattr(settings, "TELEGRAM_BOT_TOKEN", "token123")
    monkeypatch.setattr(settings, "TELEGRAM_CHAT_ID", "456")

    async def fake_send_notification(title, message, level="info"):
        return True

    monkeypatch.setattr(notifications, "send_notification", fake_send_notification)

    resp = await async_client.post("/api/notifications/test")
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"
