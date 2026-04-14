"""Shared status / error envelope helpers for integration fetchers.

Every ``fetch_*_data()`` coroutine in ``backend/integrations/`` returns a
dict the frontend can render. Three shapes exist; the helpers below
build them consistently so every integration speaks the same dialect.

**Unconfigured** (no credentials / URL yet):

    {"configured": False, ...extra}

**OK** (fetched cleanly):

    {"configured": True, "error": None, ...data}

**Failure** (configured, but the fetch blew up):

    {"configured": True, "error": "user-facing message", ...extra}

Frontend render contract:
    1. ``!data.configured``  → show "not configured" placeholder
    2. ``data.error``        → show error card (the truthy check skips
                                OK because ``error`` is ``None`` there)
    3. otherwise              → render data fields

Integrations are free to add arbitrary data keys alongside the envelope
fields; helpers accept **extra so nothing is forced.
"""

from __future__ import annotations

from typing import Any


def unconfigured(**extra: Any) -> dict:
    """No credentials / URL yet — don't alarm the user.

    Extra kwargs let callers include empty collections
    (e.g. ``containers=[]``) so the frontend render path doesn't have
    to special-case missing keys.
    """
    return {"configured": False, **extra}


def ok(**data: Any) -> dict:
    """Happy path. ``error`` is explicitly ``None`` so the frontend's
    truthy ``data.error`` check is unambiguous."""
    return {"configured": True, "error": None, **data}


def failure(message: str, **extra: Any) -> dict:
    """Fetch failed — ``message`` is user-facing (no stack traces, no
    internal paths). Extra kwargs let integrations include partial
    state (e.g. the Docker module includes ``docker_links`` even on
    failure so the frontend can still render clickable links)."""
    return {"configured": True, "error": message, **extra}
