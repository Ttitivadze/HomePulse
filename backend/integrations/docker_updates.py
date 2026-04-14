"""Container image update checking.

Compares a running container's pulled image digest against the registry's
current digest for the same tag. Exposes a single coroutine
`annotate_update_available(client, containers)` that mutates the given list
of container-info dicts in place, adding an `update_available` key:

    True  — registry digest differs from the running digest
    False — digests match (container is up to date)
    None  — unknown (unconfigured tag, registry error, or skipped to stay
            under rate limits)

Design constraints:
- Docker Hub permits 100 manifest pulls / 6h for unauthenticated clients.
  We cache every check for 6 hours and cap *uncached* registry lookups at
  MAX_CHECKS_PER_CYCLE per call so a full refresh on a busy host can't
  exhaust the budget in a single cycle. Remaining containers keep
  `update_available: None` and get checked on subsequent refreshes
  (the cache eventually fills in).
- Registry lookups happen via the blocking Docker SDK; we push them
  through `asyncio.to_thread` and run in parallel with `asyncio.gather`.
- Failures are swallowed and surfaced as `None` — the dashboard hides the
  badge for unknown states so a transient registry outage never shows
  false "update available".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend import cache
from backend.cache import TTL
from backend.config import settings

logger = logging.getLogger("homepulse.docker_updates")

# Cache policy lives in backend.cache.TTL — re-exported here for tests
# that want to assert on the actual number of seconds in use.
_CACHE_TTL_SECONDS = TTL.REGISTRY_UPDATE

# Max number of uncached registry lookups per call. Prevents a cold cache
# on a host with many containers from spiking the rate-limit budget.
MAX_CHECKS_PER_CYCLE = 3


def _registry_host(image_ref: str) -> str:
    """Return the registry host for an image reference.

    Docker's convention: the first path segment is treated as a registry
    host when it contains a ``.`` or ``:``, or is ``localhost``. Otherwise
    the image lives on Docker Hub.
    """
    if "/" in image_ref:
        head = image_ref.split("/", 1)[0]
        if "." in head or ":" in head or head == "localhost":
            return head
    return "docker.io"


def _auth_config_for(image_ref: str) -> dict | None:
    """Look up REGISTRY_AUTH for the image's registry, or None if absent.

    ``settings.REGISTRY_AUTH`` is a dict mapping registry host -> either
    ``{"username": ..., "password": ...}`` or an already-formed auth dict.
    Falls back to Docker Hub aliases (``docker.io`` / ``index.docker.io``).
    """
    auth_map = getattr(settings, "REGISTRY_AUTH", None) or {}
    if not auth_map:
        return None
    host = _registry_host(image_ref)
    if host in auth_map:
        return auth_map[host]
    # Docker Hub aliases
    if host == "docker.io" and "index.docker.io" in auth_map:
        return auth_map["index.docker.io"]
    if host == "index.docker.io" and "docker.io" in auth_map:
        return auth_map["docker.io"]
    return None


def _current_digest(container_image) -> str | None:
    """Extract the repo digest of the pulled image, if any."""
    digests = getattr(container_image, "attrs", {}).get("RepoDigests") or []
    for d in digests:
        if "@" in d:
            return d.split("@", 1)[1]
    return None


def _registry_digest(client, image_ref: str) -> str | None:
    """Fetch the registry's current digest for an image reference.

    Blocking — must be wrapped in asyncio.to_thread by the caller.
    Returns None on any error (network, auth, unknown tag).

    If REGISTRY_AUTH is configured for the image's registry host, that
    credential is passed through to the Docker SDK; otherwise we rely on
    the Docker daemon's own auth chain (anonymous for public images).
    """
    try:
        auth_config = _auth_config_for(image_ref)
        if auth_config:
            data = client.images.get_registry_data(image_ref, auth_config=auth_config)
        else:
            data = client.images.get_registry_data(image_ref)
        return getattr(data, "id", None) or data.attrs.get("Descriptor", {}).get("digest")
    except Exception as e:  # noqa: BLE001 — registry errors are expected and non-fatal
        logger.debug("Registry lookup failed for %s: %s", image_ref, e)
        return None


async def _check_one(client, container_obj, info: dict[str, Any], force: bool) -> None:
    """Populate info['update_available'] for one container (mutates in place)."""
    image_ref = info.get("image") or ""
    if not image_ref or "@" in image_ref:
        # Can't check untagged or digest-pinned images.
        info["update_available"] = None
        return

    cache_key = f"image_update:{image_ref}"
    if not force:
        cached = cache.get(cache_key, ttl=_CACHE_TTL_SECONDS)
        if cached is not None:
            info["update_available"] = cached.get("update_available")
            return

    current = _current_digest(container_obj.image)
    if not current:
        info["update_available"] = None
        return

    remote = await asyncio.to_thread(_registry_digest, client, image_ref)
    if not remote:
        info["update_available"] = None
        return

    update_available = remote != current
    info["update_available"] = update_available
    cache.put(cache_key, {"update_available": update_available})


async def annotate_update_available(client, container_objs: list, container_infos: list[dict]) -> None:
    """Fill `update_available` on each container info dict.

    - Cached results are applied to every container immediately.
    - Uncached lookups are rate-limited to MAX_CHECKS_PER_CYCLE per call;
      the rest get `update_available: None` and will be picked up on a
      later refresh cycle (round-robin over time as the cache fills).
    """
    if len(container_objs) != len(container_infos):
        # Defensive: misaligned arrays should never reach this point.
        for info in container_infos:
            info.setdefault("update_available", None)
        return

    checks_scheduled = 0
    tasks = []
    for obj, info in zip(container_objs, container_infos):
        image_ref = info.get("image") or ""
        if not image_ref or "@" in image_ref:
            info["update_available"] = None
            continue

        cache_key = f"image_update:{image_ref}"
        cached = cache.get(cache_key, ttl=_CACHE_TTL_SECONDS)
        if cached is not None:
            info["update_available"] = cached.get("update_available")
            continue

        if checks_scheduled >= MAX_CHECKS_PER_CYCLE:
            info["update_available"] = None
            continue

        tasks.append(_check_one(client, obj, info, force=True))
        checks_scheduled += 1

    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
