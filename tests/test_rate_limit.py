"""Tests for login rate limiting."""

import pytest

from backend import auth


@pytest.fixture(autouse=True)
def reset_rate_limit_state():
    """Ensure login-attempt state is isolated between tests."""
    auth._LOGIN_ATTEMPTS.clear()
    yield
    auth._LOGIN_ATTEMPTS.clear()


@pytest.mark.asyncio
async def test_login_rate_limited_after_max_attempts(init_db, async_client):
    await async_client.post("/api/auth/setup", json={"username": "admin", "password": "secret123"})

    # 5 wrong attempts → 401 each
    for _ in range(auth._MAX_ATTEMPTS):
        resp = await async_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 401

    # 6th attempt → 429 regardless of credential validity
    resp = await async_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret123"},
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_login_rate_limit_cleared_on_success(init_db, async_client):
    await async_client.post("/api/auth/setup", json={"username": "admin", "password": "secret123"})

    # A few failures (below the threshold)
    for _ in range(2):
        await async_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )

    # Successful login should clear the counter
    resp = await async_client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "secret123"},
    )
    assert resp.status_code == 200

    # After success, further failures restart from zero — 4 more wrongs should still 401 (not 429).
    for _ in range(auth._MAX_ATTEMPTS - 1):
        r = await async_client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        assert r.status_code == 401
