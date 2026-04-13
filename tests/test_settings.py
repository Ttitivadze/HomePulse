"""Tests for the settings panel (UI, services, users)."""

import pytest


# ── UI Settings ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_ui_settings_public(init_db, async_client):
    """UI settings endpoint is public — no auth required."""
    resp = await async_client.get("/api/settings/ui")
    assert resp.status_code == 200
    data = resp.json()
    assert data["accent_color"] == "#6366f1"
    assert data["font_family"] == "Inter"


@pytest.mark.asyncio
async def test_update_ui_settings_requires_admin(init_db, async_client):
    resp = await async_client.put("/api/settings/ui", json={
        "accent_color": "#ff0000",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_ui_settings(admin_token, async_client):
    resp = await async_client.put("/api/settings/ui",
        json={"accent_color": "#ff0000", "card_density": "compact"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accent_color"] == "#ff0000"
    assert data["card_density"] == "compact"


@pytest.mark.asyncio
async def test_reset_ui_settings(admin_token, async_client):
    # Change something first
    await async_client.put("/api/settings/ui",
        json={"accent_color": "#ff0000"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    # Reset
    resp = await async_client.post("/api/settings/ui/reset",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["accent_color"] == "#6366f1"


# ── User Management ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_users(admin_token, async_client):
    resp = await async_client.get("/api/settings/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 1
    assert users[0]["username"] == "admin"


@pytest.mark.asyncio
async def test_create_user(admin_token, async_client):
    resp = await async_client.post("/api/settings/users",
        json={"username": "viewer", "password": "pass123456", "is_admin": False},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["username"] == "viewer"
    assert resp.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_create_duplicate_user(admin_token, async_client):
    await async_client.post("/api/settings/users",
        json={"username": "dup", "password": "pass123456"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp = await async_client.post("/api/settings/users",
        json={"username": "dup", "password": "pass123456"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_toggle_admin(admin_token, async_client):
    # Create a regular user
    create_resp = await async_client.post("/api/settings/users",
        json={"username": "user1", "password": "pass123456"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = create_resp.json()["id"]

    # Promote
    resp = await async_client.put(f"/api/settings/users/{user_id}/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is True

    # Demote
    resp = await async_client.put(f"/api/settings/users/{user_id}/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_cannot_toggle_own_admin(admin_token, async_client):
    me = await async_client.get("/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    my_id = me.json()["id"]

    resp = await async_client.put(f"/api/settings/users/{my_id}/admin",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_user(admin_token, async_client):
    create_resp = await async_client.post("/api/settings/users",
        json={"username": "todelete", "password": "pass123456"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    user_id = create_resp.json()["id"]

    resp = await async_client.delete(f"/api/settings/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_cannot_delete_self(admin_token, async_client):
    me = await async_client.get("/api/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    my_id = me.json()["id"]

    resp = await async_client.delete(f"/api/settings/users/{my_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400


# ── Services ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_services_requires_admin(init_db, async_client):
    resp = await async_client.get("/api/settings/services")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_services(admin_token, async_client):
    resp = await async_client.get("/api/settings/services",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "RADARR_URL" in data
    assert "RADARR_API_KEY" in data
    assert data["RADARR_API_KEY"]["is_secret"] is True


@pytest.mark.asyncio
async def test_update_service_config(admin_token, async_client):
    resp = await async_client.put("/api/settings/services",
        json={"configs": {"RADARR_URL": "http://localhost:7878"}},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "updated"
