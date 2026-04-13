import asyncio
import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache

logger = logging.getLogger("homelab.proxmox")

router = APIRouter()


def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
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
    if not isinstance(vms_resp, Exception) and vms_resp.status_code == 200:
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
    if not isinstance(lxc_resp, Exception) and lxc_resp.status_code == 200:
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


async def fetch_proxmox_data() -> dict:
    """Fetch all Proxmox data. Returns a dict; never raises."""
    if not settings.PROXMOX_HOST:
        return {"configured": False, "nodes": []}

    cached = cache.get("proxmox")
    if cached is not None:
        return cached

    try:
        async with _get_client() as client:
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

            data = {"configured": True, "nodes": valid_nodes}
            cache.put("proxmox", data)
            return data

    except httpx.ConnectError:
        logger.warning("Cannot connect to Proxmox at %s", settings.PROXMOX_HOST)
        return {"configured": True, "nodes": [], "error": "Cannot connect to Proxmox host"}
    except httpx.HTTPStatusError as e:
        logger.warning("Proxmox API error: %s", e.response.status_code)
        return {"configured": True, "nodes": [], "error": "Proxmox API error"}
    except Exception as e:
        logger.exception("Proxmox fetch failed")
        return {"configured": True, "nodes": [], "error": "Proxmox request failed"}


@router.get("/status")
async def get_proxmox_status():
    """Get all nodes, VMs and LXC containers with their status."""
    data = await fetch_proxmox_data()
    if "error" in data:
        raise HTTPException(status_code=503, detail=data["error"])
    return data
