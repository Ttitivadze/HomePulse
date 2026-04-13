import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend import cache


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
