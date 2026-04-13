"""Tests for the authentication system."""

import pytest


@pytest.mark.asyncio
async def test_auth_status_needs_setup(init_db, async_client):
    resp = await async_client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is True


@pytest.mark.asyncio
async def test_setup_creates_admin(init_db, async_client):
    resp = await async_client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "secret123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["is_admin"] is True
    assert "token" in data


@pytest.mark.asyncio
async def test_setup_only_works_once(init_db, async_client):
    # First setup
    resp = await async_client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "secret123",
    })
    assert resp.status_code == 200

    # Second setup should fail
    resp = await async_client.post("/api/auth/setup", json={
        "username": "admin2",
        "password": "secret456",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_login_valid(init_db, async_client):
    # Create admin first
    await async_client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "secret123",
    })

    # Login
    resp = await async_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "secret123",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["is_admin"] is True
    assert "token" in data


@pytest.mark.asyncio
async def test_login_invalid_password(init_db, async_client):
    await async_client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "secret123",
    })

    resp = await async_client.post("/api/auth/login", json={
        "username": "admin",
        "password": "wrong",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_endpoint(admin_token, async_client):
    resp = await async_client.get("/api/auth/me", headers={
        "Authorization": f"Bearer {admin_token}",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "admin"
    assert data["is_admin"] is True


@pytest.mark.asyncio
async def test_me_endpoint_no_token(init_db, async_client):
    resp = await async_client.get("/api/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_status_after_setup(admin_token, async_client):
    resp = await async_client.get("/api/auth/status")
    assert resp.status_code == 200
    assert resp.json()["needs_setup"] is False
