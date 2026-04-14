"""Tests for external API keys."""

import pytest

from backend.config import settings
from backend.integrations import api_keys


@pytest.mark.asyncio
async def test_create_and_list_keys(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}

    # Empty list initially
    resp = await async_client.get("/api/settings/api-keys", headers=hdr)
    assert resp.status_code == 200
    assert resp.json() == []

    # Create one
    resp = await async_client.post(
        "/api/settings/api-keys",
        headers=hdr,
        json={"name": "ci"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "ci"
    key = data["key"]
    assert key.startswith("hp_")
    assert len(key) >= 11

    # Show up in list (no plaintext)
    resp = await async_client.get("/api/settings/api-keys", headers=hdr)
    keys = resp.json()
    assert len(keys) == 1
    assert keys[0]["name"] == "ci"
    assert "key" not in keys[0]
    assert "hash" not in keys[0]["key_prefix"]


@pytest.mark.asyncio
async def test_verify_api_key_success(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.post(
        "/api/settings/api-keys",
        headers=hdr,
        json={"name": "ci"},
    )
    raw = resp.json()["key"]

    row = await api_keys.verify_api_key(raw)
    assert row is not None
    assert row["name"] == "ci"


@pytest.mark.asyncio
async def test_verify_api_key_invalid(admin_token, async_client):
    row = await api_keys.verify_api_key("hp_completelymadeupkey0000000000")
    assert row is None

    row = await api_keys.verify_api_key(None)
    assert row is None

    row = await api_keys.verify_api_key("not-a-key")
    assert row is None


@pytest.mark.asyncio
async def test_revoke_api_key(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.post(
        "/api/settings/api-keys",
        headers=hdr,
        json={"name": "ci"},
    )
    key_id = resp.json()["id"]
    raw = resp.json()["key"]

    # Revoke
    resp = await async_client.delete(f"/api/settings/api-keys/{key_id}", headers=hdr)
    assert resp.status_code == 200

    # Verification should now fail
    row = await api_keys.verify_api_key(raw)
    assert row is None

    # Second revoke attempt should 404
    resp = await async_client.delete(f"/api/settings/api-keys/{key_id}", headers=hdr)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_dashboard_requires_auth_when_flag_set(admin_token, async_client, monkeypatch):
    # Create a valid key
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.post("/api/settings/api-keys", headers=hdr, json={"name": "dash"})
    raw = resp.json()["key"]

    # Flag on: anonymous access denied
    monkeypatch.setattr(settings, "DASHBOARD_REQUIRE_AUTH", True)
    resp = await async_client.get("/api/dashboard")
    assert resp.status_code == 401

    # Valid X-API-Key accepted
    resp = await async_client.get("/api/dashboard", headers={"X-API-Key": raw})
    assert resp.status_code == 200

    # JWT bearer also accepted
    resp = await async_client.get("/api/dashboard", headers=hdr)
    assert resp.status_code == 200

    # Invalid key rejected
    resp = await async_client.get("/api/dashboard", headers={"X-API-Key": "hp_invalidkey00000000"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_public_when_flag_unset(init_db, async_client, monkeypatch):
    # Default: no auth required, dashboard works anonymously.
    monkeypatch.setattr(settings, "DASHBOARD_REQUIRE_AUTH", False)
    resp = await async_client.get("/api/dashboard")
    assert resp.status_code == 200
