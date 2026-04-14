import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache, database as db
from backend.integrations._status import ok, failure, unconfigured

logger = logging.getLogger("homepulse.proxmox")

router = APIRouter()

# Module-level shared client for the default instance; created lazily, closed during app shutdown.
_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.PROXMOX_HOST,
            headers={
                "Authorization": (
                    f"PVEAPIToken={settings.PROXMOX_USER}"
                    f"!{settings.PROXMOX_TOKEN_NAME}={settings.PROXMOX_TOKEN_VALUE}"
                )
            },
            verify=settings.PROXMOX_VERIFY_SSL,
            timeout=10.0,
        )
    return _client


def _make_client(config: dict) -> httpx.AsyncClient:
    """Create an httpx client from an instance config dict."""
    host = config["host"].rstrip("/")
    user = config.get("user", "root@pam")
    token_name = config.get("token_name", "")
    token_value = config.get("token_value", "")
    verify_ssl = config.get("verify_ssl", False)
    return httpx.AsyncClient(
        base_url=host,
        headers={
            "Authorization": f"PVEAPIToken={user}!{token_name}={token_value}"
        },
        verify=bool(verify_ssl),
        timeout=10.0,
    )


async def _fetch_node_guests(
    client: httpx.AsyncClient, node_name: str
) -> tuple[list, list]:
    """Fetch VMs and LXC containers for a node concurrently."""
    vms_resp, lxc_resp = await asyncio.gather(
        client.get(f"/api2/json/nodes/{node_name}/qemu"),
        client.get(f"/api2/json/nodes/{node_name}/lxc"),
        return_exceptions=True,
    )

    vms = []
    if isinstance(vms_resp, Exception):
        logger.warning("Failed to fetch VMs for node %s: %s", node_name, vms_resp)
    elif vms_resp.status_code != 200:
        logger.warning("Proxmox VMs for node %s returned HTTP %d", node_name, vms_resp.status_code)
    else:
        for vm in vms_resp.json().get("data", []):
            vms.append(
                {
                    "vmid": vm["vmid"],
                    "name": vm.get("name", f"VM {vm['vmid']}"),
                    "status": vm.get("status", "unknown"),
                    "cpu": round(vm.get("cpu", 0) * 100, 1),
                    "mem": vm.get("mem", 0),
                    "maxmem": vm.get("maxmem", 0),
                    "uptime": vm.get("uptime", 0),
                }
            )

    containers = []
    if isinstance(lxc_resp, Exception):
        logger.warning("Failed to fetch LXC for node %s: %s", node_name, lxc_resp)
    elif lxc_resp.status_code != 200:
        logger.warning("Proxmox LXC for node %s returned HTTP %d", node_name, lxc_resp.status_code)
    else:
        for ct in lxc_resp.json().get("data", []):
            containers.append(
                {
                    "vmid": ct["vmid"],
                    "name": ct.get("name", f"CT {ct['vmid']}"),
                    "status": ct.get("status", "unknown"),
                    "cpu": round(ct.get("cpu", 0) * 100, 1),
                    "mem": ct.get("mem", 0),
                    "maxmem": ct.get("maxmem", 0),
                    "uptime": ct.get("uptime", 0),
                }
            )

    return vms, containers


async def _fetch_instance(client: httpx.AsyncClient, host_url: str) -> dict:
    """Fetch nodes from a single Proxmox instance using the given client."""
    nodes_resp = await client.get("/api2/json/nodes")
    nodes_resp.raise_for_status()
    nodes = nodes_resp.json()["data"]

    async def build_node(node):
        node_name = node["node"]
        vms, containers = await _fetch_node_guests(client, node_name)
        return {
            "name": node_name,
            "status": node.get("status", "unknown"),
            "cpu": round(node.get("cpu", 0) * 100, 1),
            "mem_used": node.get("mem", 0),
            "mem_total": node.get("maxmem", 0),
            "uptime": node.get("uptime", 0),
            "vms": vms,
            "containers": containers,
        }

    results = await asyncio.gather(
        *(build_node(n) for n in nodes),
        return_exceptions=True,
    )
    valid_nodes = [r for r in results if isinstance(r, dict)]
    return ok(nodes=valid_nodes, url=host_url)


async def fetch_proxmox_data() -> dict:
    """Fetch data from the default (env-based) Proxmox instance. Returns a dict; never raises."""
    if not settings.PROXMOX_HOST:
        return unconfigured(nodes=[])

    cached = cache.get("proxmox:default")
    if cached is not None:
        return cached

    try:
        client = await _get_client()
        data = await _fetch_instance(client, settings.PROXMOX_HOST)
        cache.put("proxmox:default", data)
        return data

    except httpx.ConnectError:
        logger.warning("Cannot connect to Proxmox at %s", settings.PROXMOX_HOST)
        return failure("Cannot connect to Proxmox host", nodes=[])
    except httpx.HTTPStatusError as e:
        logger.warning("Proxmox API error: %s", e.response.status_code)
        return failure("Proxmox API error", nodes=[])
    except Exception:
        logger.exception("Proxmox fetch failed")
        return failure("Proxmox request failed", nodes=[])


async def _fetch_additional_instance(instance_id: int, name: str, config: dict) -> dict:
    """Fetch data from an additional Proxmox instance stored in the DB."""
    cache_key = f"proxmox:{instance_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    host = config.get("host", "").rstrip("/")
    if not host:
        return unconfigured(name=name, nodes=[])

    client = _make_client(config)
    try:
        data = await _fetch_instance(client, host)
        data["name"] = name
        cache.put(cache_key, data)
        return data
    except httpx.ConnectError:
        logger.warning("Cannot connect to Proxmox instance '%s' at %s", name, host)
        return failure(f"Cannot connect to {name}", name=name, nodes=[], url=host)
    except httpx.HTTPStatusError as e:
        logger.warning("Proxmox instance '%s' API error: %s", name, e.response.status_code)
        return failure("Proxmox API error", name=name, nodes=[], url=host)
    except Exception:
        logger.exception("Proxmox instance '%s' fetch failed", name)
        return failure("Proxmox request failed", name=name, nodes=[], url=host)
    finally:
        await client.aclose()


async def fetch_all_proxmox_data() -> dict:
    """Fetch data from all Proxmox instances (default + additional). Never raises."""
    instances = []

    # Default instance from env/settings
    default_data = await fetch_proxmox_data()
    if default_data.get("configured"):
        default_data["name"] = "Default"
        instances.append(default_data)

    # Additional instances from DB
    try:
        rows = await db.fetch_all(
            "SELECT id, instance_name, config FROM service_instances WHERE service_type = 'proxmox'"
        )
    except Exception:
        logger.exception("Failed to load Proxmox instances from DB")
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
                logger.error("Proxmox instance '%s' (id=%d) failed: %s", rows[i]["instance_name"], rows[i]["id"], r)

    if not instances:
        return unconfigured(instances=[])

    return ok(instances=instances)


@router.get("/status")
async def get_proxmox_status():
    """Get all nodes, VMs and LXC containers from all Proxmox instances."""
    data = await fetch_all_proxmox_data()
    if not data.get("configured"):
        return data
    # Truthy check — with the shared error envelope every instance has
    # an `error` key (None on success, str on failure).
    errors = [inst for inst in data["instances"] if inst.get("error")]
    if len(errors) == len(data["instances"]):
        raise HTTPException(status_code=503, detail=errors[0]["error"])
    return data
