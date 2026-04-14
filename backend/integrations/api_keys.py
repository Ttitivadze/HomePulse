"""External API key management.

API keys let external tools query HomePulse read-only endpoints without a
JWT login. Keys are created by admins via the settings panel and shown
only once at creation time (hashed with bcrypt before storage).

Key format: ``hp_<24 base64url chars>`` (27 chars total).

Storage layout (see backend/database.py):
- ``key_prefix`` = first 11 chars of the raw key (``hp_`` + 8 chars). Used
  as an indexed lookup so we only bcrypt-verify matching rows — avoids
  O(n) bcrypt on every request. The prefix alone cannot authenticate.
- ``key_hash``   = bcrypt(raw_key). The raw key is never stored.

Authentication model:
- ``verify_api_key(header_value)`` returns the row on a successful match
  and updates ``last_used_at``; returns None otherwise.
- ``require_api_key_or_jwt`` is a FastAPI dependency that accepts either
  an ``X-API-Key`` header or a JWT ``Authorization: Bearer ...`` header.
  Endpoints that should gate external access behind
  ``DASHBOARD_REQUIRE_AUTH`` should add ``Depends(require_api_key_or_jwt)``.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend import database as db
from backend.auth import decode_token, require_admin

logger = logging.getLogger("homepulse.api_keys")

router = APIRouter()

_KEY_PREFIX = "hp_"
_RANDOM_LEN = 24           # base64url chars after the prefix
_PREFIX_LEN = len(_KEY_PREFIX) + 8   # full stored prefix length
_bearer = HTTPBearer(auto_error=False)


# ── Key generation / verification ───────────────────────────────────


def _generate_raw_key() -> str:
    """Return a fresh key like 'hp_<24 base64url chars>'."""
    return f"{_KEY_PREFIX}{secrets.token_urlsafe(_RANDOM_LEN)[:_RANDOM_LEN]}"


def _hash_key(raw: str) -> str:
    return bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()


def _verify_hash(raw: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode(), stored_hash.encode())
    except ValueError:
        # Malformed hash — treat as no match rather than crashing.
        return False


async def verify_api_key(raw_key: str | None) -> dict | None:
    """Return the api_keys row for ``raw_key`` if valid, else None.

    A valid key is non-revoked and matches a row's bcrypt hash. On success,
    ``last_used_at`` is updated asynchronously.
    """
    if not raw_key or not raw_key.startswith(_KEY_PREFIX) or len(raw_key) < _PREFIX_LEN:
        return None

    prefix = raw_key[:_PREFIX_LEN]
    rows = await db.fetch_all(
        "SELECT id, name, key_hash, revoked_at FROM api_keys "
        "WHERE key_prefix = ? AND revoked_at IS NULL",
        (prefix,),
    )
    for row in rows:
        if _verify_hash(raw_key, row["key_hash"]):
            # Update last_used_at — best-effort, don't fail auth if it errors.
            try:
                await db.execute(
                    "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), row["id"]),
                )
            except Exception:
                logger.exception("Failed to update last_used_at for api_key id=%s", row["id"])
            return row
    return None


# ── FastAPI dependency ──────────────────────────────────────────────


async def require_api_key_or_jwt(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Accept either a valid API key (X-API-Key) or a valid JWT bearer token.

    Returns a dict describing the principal:
        {"kind": "api_key", "id": <int>, "name": <str>}
        {"kind": "user",    "sub": <int>, "username": <str>, "is_admin": bool}
    """
    if x_api_key:
        row = await verify_api_key(x_api_key)
        if row:
            return {"kind": "api_key", "id": row["id"], "name": row["name"]}
        raise HTTPException(status_code=401, detail="Invalid API key")

    if creds:
        user = decode_token(creds.credentials)
        return {"kind": "user", **user}

    raise HTTPException(status_code=401, detail="Authentication required (X-API-Key or Bearer token)")


# ── Admin endpoints ─────────────────────────────────────────────────


class CreateKeyRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


@router.get("")
async def list_keys(admin: dict = Depends(require_admin)):
    """List all API keys (plaintext never returned). Admin only."""
    rows = await db.fetch_all(
        "SELECT id, name, key_prefix, created_at, last_used_at, revoked_at "
        "FROM api_keys ORDER BY created_at DESC"
    )
    return rows


@router.post("", status_code=201)
async def create_key(req: CreateKeyRequest, admin: dict = Depends(require_admin)):
    """Create a new API key. Plaintext key is returned exactly once."""
    raw = _generate_raw_key()
    key_id = await db.execute_returning_id(
        "INSERT INTO api_keys (name, key_prefix, key_hash, created_by) VALUES (?, ?, ?, ?)",
        (req.name, raw[:_PREFIX_LEN], _hash_key(raw), admin.get("sub")),
    )
    logger.info("API key '%s' (id=%d) created by %s", req.name, key_id, admin.get("username"))
    return {"id": key_id, "name": req.name, "key": raw, "key_prefix": raw[:_PREFIX_LEN]}


@router.delete("/{key_id}")
async def revoke_key(
    key_id: int = Path(..., ge=1),
    admin: dict = Depends(require_admin),
):
    """Revoke an API key (soft-delete via revoked_at)."""
    row = await db.fetch_one("SELECT id FROM api_keys WHERE id = ? AND revoked_at IS NULL", (key_id,))
    if not row:
        raise HTTPException(status_code=404, detail="API key not found or already revoked")
    await db.execute(
        "UPDATE api_keys SET revoked_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"), key_id),
    )
    logger.info("API key id=%d revoked by %s", key_id, admin.get("username"))
    return {"status": "revoked"}
