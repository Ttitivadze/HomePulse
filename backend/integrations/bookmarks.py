"""Bookmarks / app-launcher widget.

Admin-managed list of clickable links that appears as a section on the
dashboard. Competing homelab dashboards (Homer, Dashy, Homarr, Homepage)
all ship something like this as their flagship feature; HomePulse's
version is deliberately minimal — one flat table, optional icon and
group, no heavy config-as-YAML story.

Data model (see backend/database.py):
    id, name, url, icon (emoji or image URL), group_name, sort_order

Public read endpoint: GET /api/bookmarks → [{…}]
Admin write endpoints (mounted under /api/settings):
    POST   /api/settings/bookmarks            create
    PUT    /api/settings/bookmarks/{id}       update
    DELETE /api/settings/bookmarks/{id}       delete
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_validator

from backend import database as db
from backend.auth import require_admin

logger = logging.getLogger("homepulse.bookmarks")

# Two routers: one public (mounted at /api/bookmarks) and one admin
# (mounted under /api/settings/bookmarks). Keeping them separate makes
# the access model obvious at registration time.
public_router = APIRouter()
admin_router = APIRouter()


# ── Validation helpers ──────────────────────────────────────────────


_SAFE_URL_RE = re.compile(r"^(https?|mailto):", re.IGNORECASE)


def _validate_url(url: str) -> str:
    """Reject schemes other than http/https/mailto.

    The bookmark URL is rendered as an ``href`` on the dashboard; allowing
    ``javascript:`` or ``data:`` here would be an XSS vector even with the
    frontend's attribute escaping, because the browser executes those
    URIs on click.
    """
    u = url.strip()
    if not _SAFE_URL_RE.match(u):
        raise ValueError("URL must start with http://, https://, or mailto:")
    return u


class BookmarkCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    url: str = Field(..., min_length=1, max_length=500)
    icon: str = Field("", max_length=200)
    group_name: str = Field("", max_length=80)
    sort_order: int = Field(0, ge=0, le=9999)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str) -> str:
        return _validate_url(v)


class BookmarkUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    url: str | None = Field(None, min_length=1, max_length=500)
    icon: str | None = Field(None, max_length=200)
    group_name: str | None = Field(None, max_length=80)
    sort_order: int | None = Field(None, ge=0, le=9999)

    @field_validator("url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        return _validate_url(v) if v is not None else None


async def _fetch_bookmarks() -> list[dict]:
    return await db.fetch_all(
        "SELECT id, name, url, icon, group_name, sort_order FROM bookmarks "
        "ORDER BY group_name COLLATE NOCASE, sort_order, name COLLATE NOCASE"
    )


# ── Public endpoint ─────────────────────────────────────────────────


@public_router.get("")
async def list_bookmarks():
    """Public list — shown on the dashboard."""
    return await _fetch_bookmarks()


# ── Admin endpoints ─────────────────────────────────────────────────


@admin_router.get("")
async def admin_list_bookmarks(admin: dict = Depends(require_admin)):
    """Same shape as the public list — mirrored under /api/settings/bookmarks
    so the admin panel can reuse one fetch path."""
    return await _fetch_bookmarks()


@admin_router.post("", status_code=201)
async def create_bookmark(req: BookmarkCreate, admin: dict = Depends(require_admin)):
    bookmark_id = await db.execute_returning_id(
        "INSERT INTO bookmarks (name, url, icon, group_name, sort_order) "
        "VALUES (?, ?, ?, ?, ?)",
        (req.name, req.url, req.icon, req.group_name, req.sort_order),
    )
    logger.info("Bookmark '%s' (id=%d) created by %s", req.name, bookmark_id, admin.get("username"))
    return {
        "id": bookmark_id,
        "name": req.name,
        "url": req.url,
        "icon": req.icon,
        "group_name": req.group_name,
        "sort_order": req.sort_order,
    }


@admin_router.put("/{bookmark_id}")
async def update_bookmark(
    req: BookmarkUpdate,
    bookmark_id: int = Path(..., ge=1),
    admin: dict = Depends(require_admin),
):
    row = await db.fetch_one("SELECT id FROM bookmarks WHERE id = ?", (bookmark_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Bookmark not found")

    # Only update fields the caller actually set.
    updates = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
    if not updates:
        return {"status": "no-op"}

    set_clause = ", ".join(f"{k} = ?" for k in updates) + ", updated_at = CURRENT_TIMESTAMP"
    params = tuple(updates.values()) + (bookmark_id,)
    await db.execute(f"UPDATE bookmarks SET {set_clause} WHERE id = ?", params)
    logger.info("Bookmark %d updated by %s", bookmark_id, admin.get("username"))
    return {"status": "updated"}


@admin_router.delete("/{bookmark_id}")
async def delete_bookmark(
    bookmark_id: int = Path(..., ge=1),
    admin: dict = Depends(require_admin),
):
    row = await db.fetch_one("SELECT id FROM bookmarks WHERE id = ?", (bookmark_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Bookmark not found")
    await db.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
    logger.info("Bookmark %d deleted by %s", bookmark_id, admin.get("username"))
    return {"status": "deleted"}
