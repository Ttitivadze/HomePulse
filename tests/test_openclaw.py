import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_openclaw_status_not_configured(async_client):
    with patch("backend.integrations.openclaw.settings") as mock_settings:
        mock_settings.OPENCLAW_URL = ""
        async with async_client as client:
            resp = await client.get("/api/openclaw/status")
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}


@pytest.mark.asyncio
async def test_openclaw_chat_not_configured(async_client):
    with patch("backend.integrations.openclaw.settings") as mock_settings:
        mock_settings.OPENCLAW_URL = ""
        async with async_client as client:
            resp = await client.post(
                "/api/openclaw/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
    assert resp.status_code == 503
