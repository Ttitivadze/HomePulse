import asyncio
import json
import logging
import os

import docker
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache, database as db
from backend.integrations.docker_updates import annotate_update_available

logger = logging.getLogger("homepulse.docker")

router = APIRouter()

# Socket path used by docker.from_env()
_DOCKER_SOCKET = os.environ.get("DOCKER_HOST", "unix:///var/run/docker.sock")
_DOCKER_SOCKET_PATH = _DOCKER_SOCKET.replace("unix://", "") if _DOCKER_SOCKET.startswith("unix://") else None


def _check_socket_access() -> str | None:
    """Return an error string if the Docker socket exists but isn't accessible, else None."""
    if _DOCKER_SOCKET_PATH and os.path.exists(_DOCKER_SOCKET_PATH):
        if not os.access(_DOCKER_SOCKET_PATH, os.R_OK | os.W_OK):
            return (
                "Docker socket mounted but not accessible — add the host Docker "
                "group to the container (set DOCKER_GID in .env and restart)"
            )
    return None


def _get_client():
    try:
        client = docker.from_env()
        client.ping()
        return client
    except PermissionError:
        logger.warning("Docker socket permission denied at %s", _DOCKER_SOCKET)
        return None
    except docker.errors.DockerException as e:
        if "Permission denied" in str(e) or "PermissionError" in str(e):
            logger.warning("Docker socket permission denied: %s", e)
        else:
            logger.debug("Docker not available: %s", e)
        return None


def _get_remote_client(base_url: str, tls_verify: bool = False):
    try:
        return docker.DockerClient(base_url=base_url, tls=tls_verify)
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


async def _fetch_containers(client, host_url: str) -> dict:
    """Fetch container data from a single Docker client. Returns a dict; never raises."""
    try:
        containers = await asyncio.to_thread(client.containers.list, all=True)

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
                stats_coros.append(asyncio.to_thread(_get_container_stats, c))
            else:
                async def _default():
                    return {"cpu_percent": 0, "mem_usage": 0, "mem_limit": 0}
                stats_coros.append(_default())

        all_stats = await asyncio.gather(*stats_coros, return_exceptions=True)
        for info, stats in zip(container_info, all_stats):
            if isinstance(stats, Exception):
                stats = {"cpu_percent": 0, "mem_usage": 0, "mem_limit": 0}
            info.update(stats)

        # Annotate update_available using the registry. Cached for 6 h per
        # image ref; capped at MAX_CHECKS_PER_CYCLE uncached lookups.
        try:
            await annotate_update_available(client, containers, container_info)
        except Exception:
            logger.exception("Container update annotation failed")
            for info in container_info:
                info.setdefault("update_available", None)

        return {"configured": True, "containers": container_info, "host_url": host_url, "docker_links": settings.docker_links}
    except Exception:
        logger.exception("Docker fetch failed")
        return {"configured": True, "containers": [], "host_url": host_url, "docker_links": settings.docker_links, "error": "Docker request failed"}
    finally:
        await asyncio.to_thread(client.close)


async def fetch_docker_data() -> dict:
    """Fetch Docker container data from the local socket. Returns a dict; never raises."""
    client = await asyncio.to_thread(_get_client)
    if not client:
        # Distinguish "not mounted" from "mounted but no permissions"
        access_err = _check_socket_access()
        if access_err:
            logger.warning(access_err)
            return {"configured": True, "containers": [], "host_url": settings.DOCKER_URL, "docker_links": settings.docker_links, "error": access_err}
        return {"configured": False, "containers": []}

    cached = cache.get("docker:default", ttl=30)
    if cached is not None:
        return cached

    data = await _fetch_containers(client, settings.DOCKER_URL)
    cache.put("docker:default", data)
    return data


async def _fetch_additional_instance(instance_id: int, name: str, config: dict) -> dict:
    """Fetch container data from an additional Docker instance stored in the DB."""
    cache_key = f"docker:{instance_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    host = config.get("host", "")
    host_url = config.get("url", "")
    tls_verify = config.get("tls_verify", False)

    if not host:
        return {"name": name, "configured": False, "containers": []}

    client = await asyncio.to_thread(_get_remote_client, host, tls_verify)
    if not client:
        return {"name": name, "configured": True, "containers": [], "host_url": host_url, "error": f"Cannot connect to {name}"}

    data = await _fetch_containers(client, host_url)
    data["name"] = name
    cache.put(cache_key, data)
    return data


async def fetch_all_docker_data() -> dict:
    """Fetch container data from all Docker instances (default + additional). Never raises."""
    instances = []

    # Default instance (local socket)
    default_data = await fetch_docker_data()
    if default_data.get("configured"):
        default_data["name"] = "Default"
        instances.append(default_data)

    # Additional instances from DB
    try:
        rows = await db.fetch_all(
            "SELECT id, instance_name, config FROM service_instances WHERE service_type = 'docker'"
        )
    except Exception:
        logger.exception("Failed to load Docker instances from DB")
        rows = []

    if rows:
        tasks = []
        for row in rows:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            tasks.append(_fetch_additional_instance(row["id"], row["instance_name"], config))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, dict):
                instances.append(r)
            elif isinstance(r, Exception):
                logger.error("Docker instance '%s' (id=%d) failed: %s", rows[i]["instance_name"], rows[i]["id"], r)

    if not instances:
        return {"configured": False, "instances": []}

    return {"configured": True, "instances": instances}


@router.get("/containers")
async def get_containers():
    """List all Docker containers from all instances with status and resource info."""
    data = await fetch_all_docker_data()
    if not data.get("configured"):
        return data
    errors = [inst for inst in data["instances"] if "error" in inst]
    if len(errors) == len(data["instances"]):
        raise HTTPException(status_code=503, detail=errors[0]["error"])
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
