"""Tests for the Claude chat integration."""

import pytest

from backend.config import settings


@pytest.mark.asyncio
async def test_claude_status_unconfigured(async_client, monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")
    resp = await async_client.get("/api/claude/status")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}


@pytest.mark.asyncio
async def test_claude_status_configured(async_client, monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-test")
    resp = await async_client.get("/api/claude/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] is True
    assert data["status"] == "online"


@pytest.mark.asyncio
async def test_claude_chat_not_configured(async_client, monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "")
    resp = await async_client.post(
        "/api/claude/chat",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_claude_chat_message_role_validation(async_client, monkeypatch):
    monkeypatch.setattr(settings, "CLAUDE_API_KEY", "sk-test")
    resp = await async_client.post(
        "/api/claude/chat",
        json={"messages": [{"role": "not-a-role", "content": "hi"}]},
    )
    # Pydantic validation rejects invalid role before we reach the client.
    assert resp.status_code == 422
