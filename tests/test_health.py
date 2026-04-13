import pytest


@pytest.mark.asyncio
async def test_health(async_client):
    async with async_client as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_root_serves_html(async_client):
    async with async_client as client:
        resp = await client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
