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

logger = logging.getLogger("homepulse.docker_updates")

# 6 hours — matches Docker Hub's unauthenticated rate-limit window.
_CACHE_TTL_SECONDS = 6 * 60 * 60

# Max number of uncached registry lookups per call. Prevents a cold cache
# on a host with many containers from spiking the rate-limit budget.
MAX_CHECKS_PER_CYCLE = 3


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
    """
    try:
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
