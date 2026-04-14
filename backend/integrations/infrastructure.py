"""Infrastructure monitoring — NAS storage, backup status, SSL cert expiry."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache

logger = logging.getLogger("homepulse.infrastructure")

router = APIRouter()


def _proxmox_auth_header() -> str:
    return f"PVEAPIToken={settings.PROXMOX_USER}!{settings.PROXMOX_TOKEN_NAME}={settings.PROXMOX_TOKEN_VALUE}"


async def _fetch_nodes(client: httpx.AsyncClient) -> list:
    """Fetch list of Proxmox nodes."""
    resp = await client.get(
        f"{settings.PROXMOX_HOST}/api2/json/nodes",
        headers={"Authorization": _proxmox_auth_header()},
    )
    if resp.status_code != 200:
        return []
    return [n["node"] for n in resp.json().get("data", [])]


async def _fetch_storage_data() -> list:
    """Fetch storage info from Proxmox API (per-node for accurate usage)."""
    if not settings.PROXMOX_HOST or not settings.PROXMOX_TOKEN_VALUE:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            nodes = await _fetch_nodes(client)
            if not nodes:
                return []

            # Collect storage from all nodes, dedup by storage name
            storages = {}
            for node in nodes:
                resp = await client.get(
                    f"{settings.PROXMOX_HOST}/api2/json/nodes/{node}/storage",
                    headers={"Authorization": _proxmox_auth_header()},
                )
                if resp.status_code != 200:
                    continue

                for s in resp.json().get("data", []):
                    if not s.get("active") or not s.get("total", 0):
                        continue
                    name = s["storage"]
                    # Keep the entry with the highest total (handles shared storages)
                    if name not in storages or s.get("total", 0) > storages[name].get("total", 0):
                        storages[name] = {
                            "name": name,
                            "type": s.get("type", "unknown"),
                            "total": s.get("total", 0),
                            "used": s.get("used", 0),
                            "percent": round(s.get("used", 0) / s["total"] * 100, 1) if s.get("total") else 0,
                        }

            return sorted(storages.values(), key=lambda x: -x["percent"])
    except Exception:
        logger.exception("Storage fetch failed")
        return []


def _statvfs_usage(path: str) -> dict | None:
    """Return usage info for a locally mounted path via os.statvfs.

    Returns None if the path doesn't exist or isn't readable. Blocking
    call — must be wrapped in asyncio.to_thread by the caller.
    """
    if not os.path.isdir(path):
        return None
    try:
        st = os.statvfs(path)
    except OSError as e:
        logger.debug("statvfs failed for %s: %s", path, e)
        return None

    # f_frsize = fragment size; f_blocks = total; f_bavail = avail to non-root.
    # We intentionally use f_bavail (not f_bfree) so reports match `df -h`
    # output that users see on the host.
    block = st.f_frsize or st.f_bsize
    total = block * st.f_blocks
    avail = block * st.f_bavail
    used = total - avail
    percent = round((used / total) * 100, 1) if total else 0

    return {
        "name": os.path.basename(path.rstrip("/")) or path,
        "type": "mount",
        "total": total,
        "used": used,
        "percent": percent,
        "path": path,
    }


async def _fetch_nas_mounts() -> list:
    """Collect usage for each configured NAS / local mount."""
    mounts = settings.NAS_MOUNTS
    if not mounts:
        return []

    results = await asyncio.gather(
        *(asyncio.to_thread(_statvfs_usage, p) for p in mounts),
        return_exceptions=True,
    )
    return [r for r in results if isinstance(r, dict)]


async def _fetch_backup_data() -> list:
    """Fetch recent backup status from Proxmox storage content."""
    if not settings.PROXMOX_HOST or not settings.PROXMOX_TOKEN_VALUE:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            nodes = await _fetch_nodes(client)
            if not nodes:
                return []

            # Get VM names for display
            res_resp = await client.get(
                f"{settings.PROXMOX_HOST}/api2/json/cluster/resources",
                headers={"Authorization": _proxmox_auth_header()},
                params={"type": "vm"},
            )
            vm_names = {}
            if res_resp.status_code == 200:
                for r in res_resp.json().get("data", []):
                    vm_names[r.get("vmid")] = r.get("name", f"CT {r.get('vmid')}")

            # For each node, list backup files from local storage
            backups_by_vmid = {}
            for node in nodes:
                # Find storages that can hold backups
                stor_resp = await client.get(
                    f"{settings.PROXMOX_HOST}/api2/json/nodes/{node}/storage",
                    headers={"Authorization": _proxmox_auth_header()},
                )
                if stor_resp.status_code != 200:
                    continue

                for stor in stor_resp.json().get("data", []):
                    content_types = stor.get("content", "")
                    if "backup" not in content_types:
                        continue

                    # List backup files
                    content_resp = await client.get(
                        f"{settings.PROXMOX_HOST}/api2/json/nodes/{node}/storage/{stor['storage']}/content",
                        headers={"Authorization": _proxmox_auth_header()},
                        params={"content": "backup"},
                    )
                    if content_resp.status_code != 200:
                        continue

                    for item in content_resp.json().get("data", []):
                        vmid = item.get("vmid")
                        ctime = item.get("ctime", 0)
                        if not vmid or not ctime:
                            continue
                        # Keep most recent backup per VM
                        if vmid not in backups_by_vmid or ctime > backups_by_vmid[vmid]["_ctime"]:
                            backups_by_vmid[vmid] = {
                                "vmid": vmid,
                                "name": vm_names.get(vmid, f"CT {vmid}"),
                                "last_time": datetime.fromtimestamp(ctime, tz=timezone.utc).isoformat(),
                                "status": "ok",
                                "_ctime": ctime,
                            }

            result = []
            for b in sorted(backups_by_vmid.values(), key=lambda x: x["vmid"]):
                b.pop("_ctime", None)
                result.append(b)
            return result
    except Exception:
        logger.exception("Backup fetch failed")
        return []


async def _fetch_ssl_data() -> list:
    """Fetch SSL certificate info from NPM API."""
    if not settings.NPM_URL or not settings.NPM_API_TOKEN:
        return []

    try:
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.get(
                f"{settings.NPM_URL}/api/nginx/certificates",
                headers={"Authorization": f"Bearer {settings.NPM_API_TOKEN}"},
            )
            if resp.status_code != 200:
                return []

            certs = []
            now = datetime.now(timezone.utc)
            for cert in resp.json():
                expires_str = cert.get("expires_on", "")
                if not expires_str:
                    continue

                try:
                    # NPM returns dates like "2026-07-13 02:00:06"
                    expires = datetime.fromisoformat(expires_str.replace(" ", "T")).replace(tzinfo=timezone.utc)
                    days_left = (expires - now).days
                except (ValueError, TypeError):
                    days_left = -1

                domains = cert.get("domain_names", [])
                certs.append({
                    "name": cert.get("nice_name", ", ".join(domains[:2])),
                    "domains": domains,
                    "expires_on": expires_str,
                    "days_left": days_left,
                })
            return sorted(certs, key=lambda x: x["days_left"])
    except Exception:
        logger.exception("SSL cert fetch failed")
        return []


async def fetch_infrastructure_data() -> dict:
    """Fetch all infrastructure data. Returns a dict; never raises."""
    cached = cache.get("infrastructure", ttl=60)
    if cached is not None:
        return cached

    storage, nas, backups, ssl_certs = await asyncio.gather(
        _fetch_storage_data(),
        _fetch_nas_mounts(),
        _fetch_backup_data(),
        _fetch_ssl_data(),
        return_exceptions=True,
    )

    storage_list = storage if isinstance(storage, list) else []
    nas_list = nas if isinstance(nas, list) else []

    data = {
        "configured": True,
        # NAS mounts appear first so operators see the most concrete
        # "is my backup drive full?" signal at a glance.
        "storage": nas_list + storage_list,
        "backups": backups if isinstance(backups, list) else [],
        "ssl_certs": ssl_certs if isinstance(ssl_certs, list) else [],
    }

    # Not configured if all sections are empty
    if not data["storage"] and not data["backups"] and not data["ssl_certs"]:
        data["configured"] = False

    cache.put("infrastructure", data)
    return data


@router.get("/status")
async def get_infrastructure_status():
    return await fetch_infrastructure_data()
