"""Tests for the bookmarks / app-launcher integration."""

import pytest


@pytest.mark.asyncio
async def test_public_bookmarks_empty_on_fresh_db(init_db, async_client):
    resp = await async_client.get("/api/bookmarks")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_list_delete(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}

    # Create
    resp = await async_client.post(
        "/api/settings/bookmarks",
        headers=hdr,
        json={"name": "Plex", "url": "https://plex.example.com", "icon": "🎬", "group_name": "Media"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Plex"
    assert data["url"] == "https://plex.example.com"
    bookmark_id = data["id"]

    # Public list reflects the new bookmark
    resp = await async_client.get("/api/bookmarks")
    items = resp.json()
    assert len(items) == 1
    assert items[0]["name"] == "Plex"

    # Delete
    resp = await async_client.delete(f"/api/settings/bookmarks/{bookmark_id}", headers=hdr)
    assert resp.status_code == 200

    # Deleted bookmark 404s on subsequent delete
    resp = await async_client.delete(f"/api/settings/bookmarks/{bookmark_id}", headers=hdr)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_fields(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.post(
        "/api/settings/bookmarks",
        headers=hdr,
        json={"name": "A", "url": "https://a.example.com"},
    )
    bid = resp.json()["id"]

    resp = await async_client.put(
        f"/api/settings/bookmarks/{bid}",
        headers=hdr,
        json={"name": "A2", "group_name": "Tools"},
    )
    assert resp.status_code == 200

    items = (await async_client.get("/api/bookmarks")).json()
    assert items[0]["name"] == "A2"
    assert items[0]["group_name"] == "Tools"
    assert items[0]["url"] == "https://a.example.com"  # unchanged


@pytest.mark.asyncio
async def test_rejects_unsafe_url_scheme(admin_token, async_client):
    """javascript: / data: URLs must be rejected — they are an XSS vector."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    for bad in ("javascript:alert(1)", "data:text/html,<h1>x</h1>", "file:///etc/passwd"):
        resp = await async_client.post(
            "/api/settings/bookmarks",
            headers=hdr,
            json={"name": "x", "url": bad},
        )
        assert resp.status_code == 422, f"should reject {bad!r}"


@pytest.mark.asyncio
async def test_admin_list_requires_auth(init_db, async_client):
    resp = await async_client.get("/api/settings/bookmarks")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_path_id_validation(admin_token, async_client):
    hdr = {"Authorization": f"Bearer {admin_token}"}
    resp = await async_client.delete("/api/settings/bookmarks/0", headers=hdr)
    assert resp.status_code == 422
    resp = await async_client.delete("/api/settings/bookmarks/-5", headers=hdr)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_dashboard_includes_bookmarks(admin_token, async_client):
    """The aggregated /api/dashboard endpoint should carry a bookmarks
    section with items, so the frontend doesn't need a second request."""
    hdr = {"Authorization": f"Bearer {admin_token}"}
    await async_client.post(
        "/api/settings/bookmarks",
        headers=hdr,
        json={"name": "Z", "url": "https://z.example.com"},
    )
    resp = await async_client.get("/api/dashboard")
    data = resp.json()
    assert "bookmarks" in data
    assert data["bookmarks"]["configured"] is True
    assert len(data["bookmarks"]["items"]) == 1
