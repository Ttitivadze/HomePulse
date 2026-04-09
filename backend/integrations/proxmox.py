import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings

router = APIRouter()


def _get_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=settings.PROXMOX_HOST,
        headers={
            "Authorization": f"PVEAPIToken={settings.PROXMOX_USER}!{settings.PROXMOX_TOKEN_NAME}={settings.PROXMOX_TOKEN_VALUE}"
        },
        verify=settings.PROXMOX_VERIFY_SSL,
        timeout=10.0,
    )


@router.get("/status")
async def get_proxmox_status():
    """Get all nodes, VMs and LXC containers with their status."""
    if not settings.PROXMOX_HOST:
        return {"configured": False, "nodes": []}

    try:
        async with _get_client() as client:
            # Get nodes
            nodes_resp = await client.get("/api2/json/nodes")
            nodes_resp.raise_for_status()
            nodes = nodes_resp.json()["data"]

            result = []
            for node in nodes:
                node_name = node["node"]
                node_info = {
                    "name": node_name,
                    "status": node.get("status", "unknown"),
                    "cpu": round(node.get("cpu", 0) * 100, 1),
                    "mem_used": node.get("mem", 0),
                    "mem_total": node.get("maxmem", 0),
                    "uptime": node.get("uptime", 0),
                    "vms": [],
                    "containers": [],
                }

                # Get VMs (QEMU)
                vms_resp = await client.get(f"/api2/json/nodes/{node_name}/qemu")
                if vms_resp.status_code == 200:
                    for vm in vms_resp.json().get("data", []):
                        node_info["vms"].append({
                            "vmid": vm["vmid"],
                            "name": vm.get("name", f"VM {vm['vmid']}"),
                            "status": vm.get("status", "unknown"),
                            "cpu": round(vm.get("cpu", 0) * 100, 1),
                            "mem": vm.get("mem", 0),
                            "maxmem": vm.get("maxmem", 0),
                            "uptime": vm.get("uptime", 0),
                        })

                # Get LXC containers
                lxc_resp = await client.get(f"/api2/json/nodes/{node_name}/lxc")
                if lxc_resp.status_code == 200:
                    for ct in lxc_resp.json().get("data", []):
                        node_info["containers"].append({
                            "vmid": ct["vmid"],
                            "name": ct.get("name", f"CT {ct['vmid']}"),
                            "status": ct.get("status", "unknown"),
                            "cpu": round(ct.get("cpu", 0) * 100, 1),
                            "mem": ct.get("mem", 0),
                            "maxmem": ct.get("maxmem", 0),
                            "uptime": ct.get("uptime", 0),
                        })

                result.append(node_info)

            return {"configured": True, "nodes": result}

    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Proxmox host")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Proxmox API error")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
