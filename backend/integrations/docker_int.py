import asyncio
import logging

import docker
from fastapi import APIRouter, HTTPException

from backend.config import settings

logger = logging.getLogger("homepulse.docker")

router = APIRouter()


def _get_client():
    try:
        return docker.from_env()
    except docker.errors.DockerException:
        return None


def _get_container_stats(container) -> dict:
    """Get stats for a single container. Blocking — runs via to_thread."""
    try:
        stats = container.stats(stream=False)
        return {
            "cpu_percent": _calc_cpu_percent(stats),
            "mem_usage": stats["memory_stats"].get("usage", 0),
            "mem_limit": stats["memory_stats"].get("limit", 0),
        }
    except Exception:
        return {"cpu_percent": 0, "mem_usage": 0, "mem_limit": 0}


async def fetch_docker_data() -> dict:
    """Fetch all Docker container data. Returns a dict; never raises."""
    client = _get_client()
    if not client:
        return {"configured": False, "containers": []}

    try:
        containers = await asyncio.to_thread(client.containers.list, all=True)

        # Build base info for every container
        container_info = []
        stats_coros = []

        labels = settings.docker_labels
        for c in containers:
            info = {
                "id": c.short_id,
                "name": c.name,
                "display_name": labels.get(c.name, c.name),
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "status": c.status,
                "state": c.attrs["State"]["Status"],
                "created": c.attrs["Created"],
                "ports": _format_ports(c.ports),
            }
            container_info.append(info)

            if c.status == "running":
                # Offload blocking stats() call to a thread
                stats_coros.append(asyncio.to_thread(_get_container_stats, c))
            else:
                async def _default():
                    return {"cpu_percent": 0, "mem_usage": 0, "mem_limit": 0}
                stats_coros.append(_default())

        # Gather all stats concurrently
        all_stats = await asyncio.gather(*stats_coros, return_exceptions=True)
        for info, stats in zip(container_info, all_stats):
            if isinstance(stats, Exception):
                stats = {"cpu_percent": 0, "mem_usage": 0, "mem_limit": 0}
            info.update(stats)

        return {"configured": True, "containers": container_info, "host_url": settings.DOCKER_URL}
    except Exception as e:
        logger.exception("Docker fetch failed")
        return {"configured": True, "containers": [], "error": "Docker request failed"}
    finally:
        client.close()


@router.get("/containers")
async def get_containers():
    """List all Docker containers with status and resource info."""
    data = await fetch_docker_data()
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data


def _calc_cpu_percent(stats: dict) -> float:
    cpu_delta = (
        stats["cpu_stats"]["cpu_usage"]["total_usage"]
        - stats["precpu_stats"]["cpu_usage"]["total_usage"]
    )
    system_delta = (
        stats["cpu_stats"]["system_cpu_usage"]
        - stats["precpu_stats"]["system_cpu_usage"]
    )
    num_cpus = stats["cpu_stats"]["online_cpus"]
    if system_delta > 0 and cpu_delta > 0:
        return round((cpu_delta / system_delta) * num_cpus * 100, 1)
    return 0.0


def _format_ports(ports: dict) -> list:
    result = []
    for container_port, bindings in (ports or {}).items():
        if bindings:
            for b in bindings:
                result.append(f"{b['HostPort']}->{container_port}")
        else:
            result.append(container_port)
    return result
