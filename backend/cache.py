"""Simple in-memory TTL cache for dashboard data."""

import time
from typing import Any

_store: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 15.0  # seconds


def get(key: str, ttl: float = DEFAULT_TTL) -> Any | None:
    """Return cached value if it exists and hasn't expired, else None."""
    entry = _store.get(key)
    if entry is not None and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def put(key: str, value: Any) -> None:
    """Store a value with the current timestamp."""
    _store[key] = (time.time(), value)


def clear() -> None:
    """Flush the entire cache."""
    _store.clear()
