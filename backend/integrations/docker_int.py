import docker
from fastapi import APIRouter, HTTPException

router = APIRouter()


def _get_client():
    try:
        return docker.from_env()
    except docker.errors.DockerException:
        return None


@router.get("/containers")
async def get_containers():
    """List all Docker containers with status and resource info."""
    client = _get_client()
    if not client:
        return {"configured": False, "containers": []}

    try:
        containers = client.containers.list(all=True)
        result = []
        for c in containers:
            info = {
                "id": c.short_id,
                "name": c.name,
                "image": c.image.tags[0] if c.image.tags else c.image.short_id,
                "status": c.status,
                "state": c.attrs["State"]["Status"],
                "created": c.attrs["Created"],
                "ports": _format_ports(c.ports),
            }

            # Get resource stats for running containers
            if c.status == "running":
                try:
                    stats = c.stats(stream=False)
                    info["cpu_percent"] = _calc_cpu_percent(stats)
                    info["mem_usage"] = stats["memory_stats"].get("usage", 0)
                    info["mem_limit"] = stats["memory_stats"].get("limit", 0)
                except Exception:
                    info["cpu_percent"] = 0
                    info["mem_usage"] = 0
                    info["mem_limit"] = 0
            else:
                info["cpu_percent"] = 0
                info["mem_usage"] = 0
                info["mem_limit"] = 0

            result.append(info)

        return {"configured": True, "containers": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        client.close()


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
