"""Authentication: JWT tokens, password hashing, FastAPI dependencies."""

import logging
import os
import secrets
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from backend import database as db

logger = logging.getLogger("homepulse.auth")

router = APIRouter()

# JWT configuration
_JWT_SECRET = os.getenv("JWT_SECRET", "")
if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_urlsafe(48)
    logger.info("No JWT_SECRET set — generated ephemeral secret (sessions reset on restart)")

_JWT_ALGORITHM = "HS256"
_JWT_EXPIRY_HOURS = 24

_bearer = HTTPBearer(auto_error=False)

# ── Rate limiting ───────────────────────────────────────────────

_LOGIN_ATTEMPTS: dict[str, list[float]] = defaultdict(list)
_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60


def _check_rate_limit(ip: str) -> None:
    """Raise 429 if too many failed login attempts from this IP."""
    now = time.time()
    attempts = _LOGIN_ATTEMPTS[ip]
    # Prune old attempts
    _LOGIN_ATTEMPTS[ip] = [t for t in attempts if now - t < _WINDOW_SECONDS]
    if len(_LOGIN_ATTEMPTS[ip]) >= _MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")


def _record_failed_attempt(ip: str) -> None:
    _LOGIN_ATTEMPTS[ip].append(time.time())


# ── Password helpers ─────────────────────────────────────────────

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())


# ── JWT helpers ──────────────────────────────────────────────────

def create_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(hours=_JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        data = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        # Convert sub back to int for internal use
        data["sub"] = int(data["sub"])
        return data
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


# ── FastAPI dependencies ─────────────────────────────────────────

async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Require a valid JWT. Returns the decoded payload."""
    if creds is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return decode_token(creds.credentials)


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Require the current user to be an admin."""
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ── Request / response models ────────────────────────────────────

class SetupRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class TokenResponse(BaseModel):
    token: str
    username: str
    is_admin: bool


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=128)
    is_admin: bool = False


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/status")
async def auth_status():
    """Check if any users exist (for first-run setup detection)."""
    user = await db.fetch_one("SELECT id FROM users LIMIT 1")
    return {"needs_setup": user is None}


@router.post("/setup", response_model=TokenResponse)
async def setup(req: SetupRequest):
    """Create the first admin account. Only works when no users exist."""
    existing = await db.fetch_one("SELECT id FROM users LIMIT 1")
    if existing:
        raise HTTPException(status_code=400, detail="Setup already completed")

    pw_hash = hash_password(req.password)
    try:
        user_id = await db.execute_returning_id(
            "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, 1)",
            (req.username, pw_hash),
        )
    except Exception:
        # Race condition: another request created a user between check and insert
        raise HTTPException(status_code=400, detail="Setup already completed")
    token = create_token(user_id, req.username, True)
    logger.info("Initial admin account created: %s", req.username)
    return TokenResponse(token=token, username=req.username, is_admin=True)


# Dummy hash used for timing-safe login (prevent user enumeration via timing)
_DUMMY_HASH = bcrypt.hashpw(b"dummy", bcrypt.gensalt()).decode()


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    """Authenticate and return a JWT."""
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    user = await db.fetch_one(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username = ?",
        (req.username,),
    )
    if not user:
        # Timing-safe: always run bcrypt even for non-existent users
        verify_password(req.password, _DUMMY_HASH)
        _record_failed_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(req.password, user["password_hash"]):
        _record_failed_attempt(client_ip)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Clear attempts on successful login
    _LOGIN_ATTEMPTS.pop(client_ip, None)
    token = create_token(user["id"], user["username"], bool(user["is_admin"]))
    return TokenResponse(
        token=token, username=user["username"], is_admin=bool(user["is_admin"])
    )


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    """Return current user info from the JWT."""
    return {
        "id": user["sub"],
        "username": user["username"],
        "is_admin": user["is_admin"],
    }
