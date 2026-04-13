import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Use an in-memory or temp DB for tests
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")

from backend.main import app
from backend import cache
from backend import database as db


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the TTL cache before each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def async_client():
    """Provide an httpx AsyncClient wired to the FastAPI app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def init_db(tmp_path):
    """Initialize a fresh test database."""
    import backend.database as db_mod
    db_mod._DB_PATH = tmp_path / "test.db"
    await db.init_db()
    yield
    # Clean up
    db_mod._DB_PATH = None


@pytest_asyncio.fixture
async def admin_token(init_db, async_client):
    """Create an admin account and return the JWT token."""
    resp = await async_client.post("/api/auth/setup", json={
        "username": "admin",
        "password": "testpass123",
    })
    data = resp.json()
    return data["token"]
