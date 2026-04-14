"""Simple in-memory TTL cache for dashboard data.

The cache is keyed by string (one key per service/instance). TTLs are
passed per-`get()` so callers can choose a policy appropriate to the
data they're looking up.

Named policies live in `TTL` below so every caller references a single
source of truth. Ad-hoc numeric TTLs in integration code are a code
smell — add a new named constant instead.
"""

import time
from typing import Any, Final

_store: dict[str, tuple[float, Any]] = {}
DEFAULT_TTL = 15.0  # seconds — general fallback for short-lived lookups


class TTL:
    """Named cache-TTL policies (seconds).

    Constants (not an Enum) so call sites read naturally:
        cache.get("docker:default", ttl=TTL.DOCKER_STATS)

    Keep these centralised so cache-coherency is reviewable in one place.
    The overarching constraint is that most TTLs should be <= the
    dashboard refresh cycle (30 s by default) unless the data is
    genuinely expensive to fetch (registry digests) or rate-limited
    (container updates / infra / uptime).
    """

    # Short: touched on every dashboard refresh. Absorbs dedup during
    # the in-flight window of a single `/api/dashboard` fetch.
    DASHBOARD: Final[float] = 15.0

    # Docker socket stats (CPU/mem) are expensive to collect but change
    # slowly at 30 s cadence; caching for 30 s halves socket pressure.
    DOCKER_STATS: Final[float] = 30.0

    # Uptime Kuma / service-reachability probes.
    UPTIME_KUMA: Final[float] = 30.0

    # Infrastructure (Proxmox storage, backups, SSL certs, NAS mounts)
    # changes at minute+ granularity.
    INFRASTRUCTURE: Final[float] = 60.0

    # Registry digest lookups: Docker Hub permits 100 manifest pulls
    # per 6 h unauthenticated. Cache for the full window so the
    # MAX_CHECKS_PER_CYCLE cap only bites on cold starts.
    REGISTRY_UPDATE: Final[float] = 6 * 60 * 60


def get(key: str, ttl: float = DEFAULT_TTL) -> Any | None:
    """Return cached value if it exists and hasn't expired, else None."""
    entry = _store.get(key)
    if entry is not None:
        if time.time() - entry[0] < ttl:
            return entry[1]
        del _store[key]  # Clean up expired entry
    return None


def put(key: str, value: Any) -> None:
    """Store a value with the current timestamp."""
    _store[key] = (time.time(), value)


def clear() -> None:
    """Flush the entire cache."""
    _store.clear()
