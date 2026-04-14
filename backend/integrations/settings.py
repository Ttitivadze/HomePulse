"""Admin settings: UI customization, service config, and user management."""

import json
import logging
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend import database as db
from backend.auth import (
    CreateUserRequest,
    hash_password,
    require_admin,
    create_token,
)

# Regex for validating CSS color values (#hex, rgb(), hsl())
_COLOR_RE = re.compile(r'^#[0-9a-fA-F]{3,8}$|^rgba?\([\d\s,.%]+\)$|^hsla?\([\d\s,.%]+\)$')

logger = logging.getLogger("homepulse.settings")

router = APIRouter()

# ── UI Settings ──────────────────────────────────────────────────

# Valid font families the UI supports
VALID_FONTS = [
    "Inter",
    "JetBrains Mono",
    "system-ui",
    "Roboto",
    "Fira Sans",
]

VALID_DENSITIES = ["compact", "comfortable"]
VALID_SECTIONS = ["proxmox", "docker", "arr", "streaming", "uptime_kuma", "infrastructure"]


def _validate_color(value: str, field_name: str) -> None:
    if not _COLOR_RE.match(value):
        raise HTTPException(status_code=400, detail=f"Invalid color for {field_name}: must be a hex (#rrggbb) or rgb/hsl value")


class UISettingsUpdate(BaseModel):
    accent_color: str | None = Field(None, max_length=20)
    bg_primary: str | None = Field(None, max_length=20)
    bg_secondary: str | None = Field(None, max_length=20)
    bg_card: str | None = Field(None, max_length=20)
    text_primary: str | None = Field(None, max_length=20)
    font_family: str | None = Field(None, max_length=50)
    card_density: str | None = Field(None, max_length=20)
    section_order: list[str] | None = None


@router.get("/ui")
async def get_ui_settings():
    """Get global UI settings. Public endpoint — no auth required."""
    row = await db.fetch_one("SELECT * FROM ui_settings WHERE id = 1")
    if not row:
        return {}
    result = dict(row)
    result.pop("id", None)
    result.pop("updated_at", None)
    # Parse section_order from JSON string
    if isinstance(result.get("section_order"), str):
        try:
            result["section_order"] = json.loads(result["section_order"])
        except (json.JSONDecodeError, TypeError):
            result["section_order"] = ["proxmox", "docker", "arr", "streaming"]
    return result


@router.put("/ui")
async def update_ui_settings(
    req: UISettingsUpdate,
    admin: dict = Depends(require_admin),
):
    """Update global UI settings. Admin only."""
    updates = {}
    color_fields = {
        "accent_color": req.accent_color,
        "bg_primary": req.bg_primary,
        "bg_secondary": req.bg_secondary,
        "bg_card": req.bg_card,
        "text_primary": req.text_primary,
    }
    for field, value in color_fields.items():
        if value is not None:
            _validate_color(value, field)
            updates[field] = value
    if req.font_family is not None:
        if req.font_family not in VALID_FONTS:
            raise HTTPException(status_code=400, detail=f"Invalid font. Choose from: {VALID_FONTS}")
        updates["font_family"] = req.font_family
    if req.card_density is not None:
        if req.card_density not in VALID_DENSITIES:
            raise HTTPException(status_code=400, detail=f"Invalid density. Choose from: {VALID_DENSITIES}")
        updates["card_density"] = req.card_density
    if req.section_order is not None:
        invalid = [s for s in req.section_order if s not in VALID_SECTIONS]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid sections: {invalid}. Choose from: {VALID_SECTIONS}")
        updates["section_order"] = json.dumps(req.section_order)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values())
    await db.execute(
        f"UPDATE ui_settings SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        tuple(values),
    )
    logger.info("UI settings updated by %s", admin["username"])
    return await get_ui_settings()


@router.post("/ui/reset")
async def reset_ui_settings(admin: dict = Depends(require_admin)):
    """Reset UI settings to defaults. Admin only."""
    await db.execute("""
        UPDATE ui_settings SET
            accent_color = '#6366f1',
            bg_primary = '#0f1117',
            bg_secondary = '#1a1d27',
            bg_card = '#1e2130',
            text_primary = '#e4e6f0',
            font_family = 'Inter',
            card_density = 'comfortable',
            section_order = '["proxmox","docker","arr","streaming"]',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """)
    logger.info("UI settings reset to defaults by %s", admin["username"])
    return await get_ui_settings()


# ── Service Configuration ────────────────────────────────────────

# Services manageable via the web UI
SERVICE_KEYS = [
    "PROXMOX_HOST", "PROXMOX_USER", "PROXMOX_TOKEN_NAME", "PROXMOX_TOKEN_VALUE", "PROXMOX_VERIFY_SSL",
    "DOCKER_URL",
    "RADARR_URL", "RADARR_API_KEY",
    "SONARR_URL", "SONARR_API_KEY",
    "LIDARR_URL", "LIDARR_API_KEY",
    "JELLYFIN_URL", "JELLYFIN_API_KEY",
    "PLEX_URL", "PLEX_TOKEN",
    "TAUTULLI_URL", "TAUTULLI_API_KEY",
    "CLAUDE_API_KEY", "CLAUDE_MODEL",
    "UPTIME_KUMA_URL",
    "NPM_URL", "NPM_API_TOKEN",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
    "REFRESH_INTERVAL",
]

# Keys whose values should be masked in GET responses
SECRET_KEYS = {
    "PROXMOX_TOKEN_VALUE", "RADARR_API_KEY", "SONARR_API_KEY", "LIDARR_API_KEY",
    "JELLYFIN_API_KEY", "PLEX_TOKEN", "TAUTULLI_API_KEY", "CLAUDE_API_KEY",
    "NPM_API_TOKEN", "TELEGRAM_BOT_TOKEN",
}


class ServiceConfigUpdate(BaseModel):
    configs: dict[str, str] = Field(..., description="Key-value pairs of service settings")


@router.get("/services")
async def get_service_configs(admin: dict = Depends(require_admin)):
    """Get all service configs. Secrets are masked. Admin only."""
    rows = await db.fetch_all("SELECT key, value FROM service_config")
    overrides = {r["key"]: r["value"] for r in rows}

    result = {}
    for key in SERVICE_KEYS:
        value = overrides.get(key, "")
        has_override = key in overrides
        masked = key in SECRET_KEYS and value
        result[key] = {
            "value": "••••••••" if masked else value,
            "has_override": has_override,
            "is_secret": key in SECRET_KEYS,
        }
    return result


@router.put("/services")
async def update_service_configs(
    req: ServiceConfigUpdate,
    admin: dict = Depends(require_admin),
):
    """Update service configuration overrides. Admin only."""
    for key, value in req.configs.items():
        if key not in SERVICE_KEYS:
            raise HTTPException(status_code=400, detail=f"Unknown config key: {key}")
        # Skip masked values (user didn't change them)
        if value == "••••••••":
            continue
        if value == "":
            # Empty = remove override, fall back to .env
            await db.execute("DELETE FROM service_config WHERE key = ?", (key,))
        else:
            await db.execute(
                "INSERT INTO service_config (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP",
                (key, value, value),
            )
    # Hot-reload settings so changes take effect without restart
    from backend.config import settings as _settings
    _settings.reload()
    logger.info("Service configs updated by %s (settings reloaded)", admin["username"])
    return {"status": "updated"}


@router.post("/services/test")
async def test_service_connection(
    service: str = "",
    admin: dict = Depends(require_admin),
):
    """Test connectivity to a specific service. Admin only."""
    # Fetch the current effective config
    row = await db.fetch_one("SELECT value FROM service_config WHERE key = ?", (f"{service}_URL",))
    if not row and service != "PROXMOX":
        row = await db.fetch_one("SELECT value FROM service_config WHERE key = ?", (f"{service}_HOST",))

    url = row["value"] if row else ""
    if not url:
        return {"status": "not_configured", "message": "URL not set"}

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(url)
            return {"status": "ok", "code": resp.status_code}
    except httpx.ConnectError:
        return {"status": "error", "message": "Connection refused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Service Instances (multi-instance Proxmox / Docker) ─────────

VALID_INSTANCE_TYPES = {"proxmox", "docker"}

# Secret keys inside instance config JSON blobs
_INSTANCE_SECRET_KEYS = {"token_value"}


class InstanceCreate(BaseModel):
    service_type: str = Field(..., max_length=20)
    instance_name: str = Field(..., min_length=1, max_length=50)
    config: dict = Field(default_factory=dict)


class InstanceUpdate(BaseModel):
    instance_name: str | None = Field(None, min_length=1, max_length=50)
    config: dict | None = None


def _mask_instance_config(config: dict) -> dict:
    """Return a copy of instance config with secret values masked."""
    masked = dict(config)
    for key in _INSTANCE_SECRET_KEYS:
        if key in masked and masked[key]:
            masked[key] = "••••••••"
    return masked


@router.get("/instances")
async def list_instances(admin: dict = Depends(require_admin)):
    """List all additional service instances. Admin only."""
    rows = await db.fetch_all(
        "SELECT id, service_type, instance_name, config, created_at FROM service_instances ORDER BY created_at"
    )
    result = []
    for r in rows:
        config = json.loads(r["config"]) if isinstance(r["config"], str) else r["config"]
        result.append({
            "id": r["id"],
            "service_type": r["service_type"],
            "instance_name": r["instance_name"],
            "config": _mask_instance_config(config),
            "created_at": r["created_at"],
        })
    return result


@router.post("/instances")
async def create_instance(
    req: InstanceCreate,
    admin: dict = Depends(require_admin),
):
    """Create a new service instance. Admin only."""
    if req.service_type not in VALID_INSTANCE_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid service type. Choose from: {sorted(VALID_INSTANCE_TYPES)}")

    if req.service_type == "proxmox" and not req.config.get("host"):
        raise HTTPException(status_code=400, detail="Proxmox instance requires 'host' in config")
    if req.service_type == "docker" and not req.config.get("host"):
        raise HTTPException(status_code=400, detail="Docker instance requires 'host' in config")

    config_json = json.dumps(req.config)
    instance_id = await db.execute_returning_id(
        "INSERT INTO service_instances (service_type, instance_name, config) VALUES (?, ?, ?)",
        (req.service_type, req.instance_name, config_json),
    )
    logger.info("Instance '%s' (%s) created by %s", req.instance_name, req.service_type, admin["username"])
    return {"id": instance_id, "service_type": req.service_type, "instance_name": req.instance_name}


@router.put("/instances/{instance_id}")
async def update_instance(
    instance_id: int,
    req: InstanceUpdate,
    admin: dict = Depends(require_admin),
):
    """Update a service instance. Admin only."""
    row = await db.fetch_one("SELECT * FROM service_instances WHERE id = ?", (instance_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Instance not found")

    if req.instance_name is not None:
        await db.execute(
            "UPDATE service_instances SET instance_name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (req.instance_name, instance_id),
        )

    if req.config is not None:
        # Start from existing config, overlay user changes, preserve masked secrets
        existing_config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        merged = dict(existing_config)
        for key, value in req.config.items():
            if key in _INSTANCE_SECRET_KEYS and value == "••••••••":
                continue  # Preserve existing secret
            merged[key] = value
        await db.execute(
            "UPDATE service_instances SET config = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(merged), instance_id),
        )

    logger.info("Instance %d updated by %s", instance_id, admin["username"])
    return {"status": "updated"}


@router.delete("/instances/{instance_id}")
async def delete_instance(
    instance_id: int,
    admin: dict = Depends(require_admin),
):
    """Delete a service instance. Admin only."""
    row = await db.fetch_one("SELECT id FROM service_instances WHERE id = ?", (instance_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Instance not found")

    await db.execute("DELETE FROM service_instances WHERE id = ?", (instance_id,))
    logger.info("Instance %d deleted by %s", instance_id, admin["username"])
    return {"status": "deleted"}


@router.post("/instances/{instance_id}/test")
async def test_instance_connection(
    instance_id: int,
    admin: dict = Depends(require_admin),
):
    """Test connectivity to a service instance. Admin only."""
    row = await db.fetch_one("SELECT * FROM service_instances WHERE id = ?", (instance_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Instance not found")

    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    url = config.get("host", "")
    if not url:
        return {"status": "not_configured", "message": "Host not set"}

    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(url)
            return {"status": "ok", "code": resp.status_code}
    except httpx.ConnectError:
        return {"status": "error", "message": "Connection refused"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── User Management ──────────────────────────────────────────────

@router.get("/users")
async def list_users(admin: dict = Depends(require_admin)):
    """List all user accounts. Admin only."""
    rows = await db.fetch_all(
        "SELECT id, username, is_admin, created_at FROM users ORDER BY created_at"
    )
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "is_admin": bool(r["is_admin"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.post("/users")
async def create_user(
    req: CreateUserRequest,
    admin: dict = Depends(require_admin),
):
    """Create a new user account. Admin only."""
    existing = await db.fetch_one(
        "SELECT id FROM users WHERE username = ?", (req.username,)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    pw_hash = hash_password(req.password)
    user_id = await db.execute_returning_id(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
        (req.username, pw_hash, int(req.is_admin)),
    )
    logger.info("User '%s' created by %s", req.username, admin["username"])
    return {"id": user_id, "username": req.username, "is_admin": req.is_admin}


@router.put("/users/{user_id}/admin")
async def toggle_admin(
    user_id: int,
    admin: dict = Depends(require_admin),
):
    """Toggle admin status for a user. Cannot change own status. Admin only."""
    if user_id == admin["sub"]:
        raise HTTPException(status_code=400, detail="Cannot change your own admin status")

    user = await db.fetch_one("SELECT id, is_admin FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_status = 0 if user["is_admin"] else 1
    await db.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_status, user_id))
    logger.info("User %d admin status changed to %s by %s", user_id, bool(new_status), admin["username"])
    return {"id": user_id, "is_admin": bool(new_status)}


class ResetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)


@router.put("/users/{user_id}/password")
async def reset_password(
    user_id: int,
    req: ResetPasswordRequest,
    admin: dict = Depends(require_admin),
):
    """Reset a user's password. Admin only."""
    user = await db.fetch_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pw_hash = hash_password(req.password)
    await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
    logger.info("Password reset for user %d by %s", user_id, admin["username"])
    return {"status": "password_reset"}


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    admin: dict = Depends(require_admin),
):
    """Delete a user account. Cannot delete yourself. Admin only."""
    if user_id == admin["sub"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    user = await db.fetch_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    logger.info("User %d deleted by %s", user_id, admin["username"])
    return {"status": "deleted"}
