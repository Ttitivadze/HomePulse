import time
from backend import cache


def test_put_and_get():
    cache.put("key1", {"data": 42})
    assert cache.get("key1") == {"data": 42}


def test_get_returns_none_for_missing_key():
    assert cache.get("nonexistent") is None


def test_get_returns_none_after_expiry():
    cache.put("key2", "value")
    # Expired with a TTL of 0
    assert cache.get("key2", ttl=0.0) is None


def test_clear_removes_all():
    cache.put("a", 1)
    cache.put("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
