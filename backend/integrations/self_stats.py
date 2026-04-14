"""Self-monitoring: the HomePulse container's own CPU / RAM / uptime.

Scrapes ``/proc`` directly — no extra dependency. Works in any Linux
container; on macOS / BSD / Windows the ``/proc`` files are missing
and the integration degrades to ``configured: False`` instead of
crashing.

Why no ``psutil`` dependency? This module only needs a handful of
numbers that ``/proc`` exposes as plain text, and an extra C-extension
dep isn't worth the install-size / cross-platform cost.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from fastapi import APIRouter

from backend import cache
from backend.cache import TTL
from backend.integrations._status import ok, unconfigured

logger = logging.getLogger("homepulse.self_stats")

router = APIRouter()

_PROC = Path("/proc")
_BOOT_TIME: float | None = None  # populated on first successful read


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text()
    except (OSError, PermissionError):
        return None


def _read_uptime() -> float | None:
    """Seconds since system boot. Returns None if /proc/uptime is absent."""
    txt = _read_text(_PROC / "uptime")
    if not txt:
        return None
    try:
        return float(txt.split()[0])
    except (ValueError, IndexError):
        return None


def _read_meminfo() -> dict | None:
    """Parse /proc/meminfo into a small dict of relevant values (bytes)."""
    txt = _read_text(_PROC / "meminfo")
    if not txt:
        return None
    vals: dict[str, int] = {}
    for line in txt.splitlines():
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        parts = rest.strip().split()
        if not parts:
            continue
        try:
            num_kb = int(parts[0])
        except ValueError:
            continue
        # Values in meminfo are in kB by convention; convert to bytes.
        vals[key] = num_kb * 1024
    if "MemTotal" not in vals:
        return None
    return vals


def _read_loadavg() -> tuple[float, float, float] | None:
    """Return the 1/5/15 min load averages, or None if unavailable."""
    txt = _read_text(_PROC / "loadavg")
    if not txt:
        return None
    try:
        parts = txt.split()
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except (ValueError, IndexError):
        return None


def _read_self_status_rss() -> int | None:
    """Resident-set size of THIS process in bytes, via /proc/self/status."""
    txt = _read_text(_PROC / "self" / "status")
    if not txt:
        return None
    for line in txt.splitlines():
        if line.startswith("VmRSS:"):
            try:
                return int(line.split()[1]) * 1024
            except (ValueError, IndexError):
                return None
    return None


def _process_uptime_seconds() -> float | None:
    """Approximate uptime of the HomePulse process in seconds."""
    global _BOOT_TIME
    # /proc/self/stat field 22 = starttime in clock ticks since boot.
    stat = _read_text(_PROC / "self" / "stat")
    sys_uptime = _read_uptime()
    if not stat or sys_uptime is None:
        return None
    try:
        # Fields 2 and 3 can contain parens; skip by finding the last ')'.
        rest = stat[stat.rfind(")") + 1:].split()
        starttime_ticks = int(rest[19])
    except (ValueError, IndexError):
        return None
    try:
        clk_tck = os.sysconf("SC_CLK_TCK")
    except (ValueError, OSError):
        clk_tck = 100  # POSIX default
    process_age = sys_uptime - (starttime_ticks / clk_tck)
    return max(process_age, 0.0)


async def fetch_self_stats_data() -> dict:
    """Collect self-stats (blocking reads are fine — /proc is in-memory)."""
    cached = cache.get("self_stats", ttl=TTL.DASHBOARD)
    if cached is not None:
        return cached

    def _collect() -> dict:
        mem = _read_meminfo()
        load = _read_loadavg()
        sys_uptime = _read_uptime()
        proc_uptime = _process_uptime_seconds()
        rss = _read_self_status_rss()

        if mem is None and load is None and sys_uptime is None:
            return unconfigured()

        mem_total = mem.get("MemTotal") if mem else None
        # Prefer MemAvailable (kernel 3.14+) — it's what `free` reports as
        # "available" and accounts for reclaimable caches. Fall back to
        # MemFree + Buffers + Cached if the newer field isn't present.
        mem_available = None
        if mem:
            if "MemAvailable" in mem:
                mem_available = mem["MemAvailable"]
            else:
                mem_available = (
                    mem.get("MemFree", 0) + mem.get("Buffers", 0) + mem.get("Cached", 0)
                )
        mem_used = (mem_total - mem_available) if (mem_total and mem_available is not None) else None
        mem_pct = round(mem_used / mem_total * 100, 1) if mem_total and mem_used is not None else None

        data = ok(
            system_uptime_s=sys_uptime,
            process_uptime_s=proc_uptime,
            load_1=load[0] if load else None,
            load_5=load[1] if load else None,
            load_15=load[2] if load else None,
            cpu_count=os.cpu_count(),
            mem_total=mem_total,
            mem_used=mem_used,
            mem_percent=mem_pct,
            process_rss=rss,
            sampled_at=time.time(),
        )
        return data

    data = await asyncio.to_thread(_collect)
    cache.put("self_stats", data)
    return data


@router.get("/status")
async def get_self_stats():
    return await fetch_self_stats_data()
