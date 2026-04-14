"""Uptime Kuma integration — monitor status dashboard widget.

Two levels of integration:
1. **Ping check**: a simple reachability probe of `/api/entry-page`
   that returns online / degraded / offline. Works anonymously.
2. **Per-monitor status** (optional): if `UPTIME_KUMA_METRICS_TOKEN`
   is set, we pull the Prometheus `/metrics` endpoint via HTTP Basic
   Auth (any username, token as password) and parse the
   `monitor_status`, `monitor_response_time`, and
   `monitor_cert_days_remaining` gauges to produce a per-monitor list.

The parser is a minimal regex-based implementation for the Prometheus
text format. It intentionally doesn't handle the long tail of escape
sequences — Uptime Kuma label values are simple enough in practice.
On any parse or network error the monitor list is returned empty so
the widget degrades to the ping-only view.
"""

from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings
from backend import cache
from backend.cache import TTL

logger = logging.getLogger("homepulse.uptime_kuma")

router = APIRouter()

# Prometheus text-format line parser. Captures metric name, labels blob,
# and value. Ignores # HELP / # TYPE comment lines.
_METRIC_LINE_RE = re.compile(r'^([a-zA-Z_][a-zA-Z0-9_]*)\{(.*?)\}\s+(\S+)\s*$')
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')

# Uptime Kuma's monitor_status values.
_STATUS_MAP = {
    "0": "down",
    "1": "up",
    "2": "pending",
    "3": "maintenance",
}


def _parse_labels(blob: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in _LABEL_RE.finditer(blob)}


def _parse_metrics_text(text: str) -> list[dict]:
    """Parse a Uptime Kuma /metrics response into a list of monitor dicts.

    Returns [] if nothing parseable is found.
    """
    monitors: dict[str, dict] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        m = _METRIC_LINE_RE.match(line)
        if not m:
            continue
        name, label_blob, value = m.group(1), m.group(2), m.group(3)
        if name not in ("monitor_status", "monitor_response_time", "monitor_cert_days_remaining"):
            continue
        labels = _parse_labels(label_blob)
        monitor_name = labels.get("monitor_name") or labels.get("monitor_url")
        if not monitor_name:
            continue
        entry = monitors.setdefault(
            monitor_name,
            {
                "name": monitor_name,
                "type": labels.get("monitor_type", ""),
                "url": labels.get("monitor_url", ""),
                "status": "unknown",
                "response_time_ms": None,
                "cert_days_remaining": None,
            },
        )
        if name == "monitor_status":
            entry["status"] = _STATUS_MAP.get(value, "unknown")
        elif name == "monitor_response_time":
            try:
                entry["response_time_ms"] = round(float(value))
            except ValueError:
                pass
        elif name == "monitor_cert_days_remaining":
            try:
                entry["cert_days_remaining"] = round(float(value))
            except ValueError:
                pass

    # Sort: down > pending > maintenance > up (most urgent first)
    urgency = {"down": 0, "pending": 1, "maintenance": 2, "up": 3, "unknown": 4}
    return sorted(monitors.values(), key=lambda r: (urgency.get(r["status"], 5), r["name"]))


async def _fetch_monitors() -> list[dict]:
    """Pull and parse Uptime Kuma /metrics. Returns [] on any error."""
    if not settings.UPTIME_KUMA_URL or not settings.UPTIME_KUMA_METRICS_TOKEN:
        return []

    try:
        auth = httpx.BasicAuth(username="metrics", password=settings.UPTIME_KUMA_METRICS_TOKEN)
        async with httpx.AsyncClient(timeout=5.0, verify=False, auth=auth) as client:
            resp = await client.get(f"{settings.UPTIME_KUMA_URL}/metrics")
            if resp.status_code != 200:
                logger.debug("Uptime Kuma /metrics returned HTTP %s", resp.status_code)
                return []
            return _parse_metrics_text(resp.text)
    except Exception:
        logger.exception("Uptime Kuma metrics fetch failed")
        return []


async def fetch_uptime_kuma_data() -> dict:
    """Fetch Uptime Kuma status. Returns a dict; never raises."""
    if not settings.UPTIME_KUMA_URL:
        return {"configured": False}

    cached = cache.get("uptime_kuma", ttl=TTL.UPTIME_KUMA)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(f"{settings.UPTIME_KUMA_URL}/api/entry-page")
            if resp.status_code == 200:
                status = "online"
            else:
                status = "degraded"
    except httpx.ConnectError:
        data = {
            "configured": True,
            "status": "offline",
            "url": settings.UPTIME_KUMA_URL,
            "monitors": [],
        }
        cache.put("uptime_kuma", data)
        return data
    except Exception:
        logger.exception("Uptime Kuma fetch failed")
        data = {
            "configured": True,
            "status": "error",
            "url": settings.UPTIME_KUMA_URL,
            "monitors": [],
        }
        cache.put("uptime_kuma", data)
        return data

    # Only try per-monitor fetch when the base ping succeeded — no point
    # hammering /metrics if the whole service is offline.
    monitors = await _fetch_monitors()

    data = {
        "configured": True,
        "status": status,
        "url": settings.UPTIME_KUMA_URL,
        "monitors": monitors,
        # Quick count summary for the header badge.
        "summary": {
            "up": sum(1 for m in monitors if m["status"] == "up"),
            "down": sum(1 for m in monitors if m["status"] == "down"),
            "total": len(monitors),
        },
    }
    cache.put("uptime_kuma", data)
    return data


@router.get("/status")
async def get_uptime_kuma_status():
    data = await fetch_uptime_kuma_data()
    if not data.get("configured"):
        return data
    if data.get("status") == "offline":
        raise HTTPException(status_code=503, detail="Uptime Kuma is offline")
    return data
