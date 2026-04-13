"""SQLite database for user accounts, UI settings, and service config overrides."""

import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger("homepulse.database")

_DB_PATH: Path | None = None
_lock = asyncio.Lock()


def _resolve_db_path() -> Path:
    """Determine database file location."""
    for candidate in [Path("data"), Path("/app/data")]:
        if candidate.is_dir():
            return candidate / "homepulse.db"
    # Default: create data/ next to project root
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    return data_dir / "homepulse.db"


def _get_connection() -> sqlite3.Connection:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = _resolve_db_path()
    conn = sqlite3.connect(str(_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            is_admin INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ui_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            accent_color TEXT DEFAULT '#6366f1',
            bg_primary TEXT DEFAULT '#0f1117',
            bg_secondary TEXT DEFAULT '#1a1d27',
            bg_card TEXT DEFAULT '#1e2130',
            text_primary TEXT DEFAULT '#e4e6f0',
            font_family TEXT DEFAULT 'Inter',
            card_density TEXT DEFAULT 'comfortable',
            section_order TEXT DEFAULT '["proxmox","docker","arr","streaming"]',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS service_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        -- Ensure exactly one UI settings row exists
        INSERT OR IGNORE INTO ui_settings (id) VALUES (1);
    """)


async def init_db() -> None:
    """Initialize the database schema. Called once at app startup."""
    def _do():
        conn = _get_connection()
        try:
            _init_schema(conn)
            conn.commit()
            logger.info("Database initialized at %s", _DB_PATH)
        finally:
            conn.close()
    await asyncio.to_thread(_do)


async def execute(sql: str, params: tuple = ()) -> None:
    async with _lock:
        def _do():
            conn = _get_connection()
            try:
                conn.execute(sql, params)
                conn.commit()
            finally:
                conn.close()
        await asyncio.to_thread(_do)


async def execute_returning_id(sql: str, params: tuple = ()) -> int:
    async with _lock:
        def _do():
            conn = _get_connection()
            try:
                cursor = conn.execute(sql, params)
                conn.commit()
                return cursor.lastrowid
            finally:
                conn.close()
        return await asyncio.to_thread(_do)


async def fetch_one(sql: str, params: tuple = ()) -> dict | None:
    def _do():
        conn = _get_connection()
        try:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()
    return await asyncio.to_thread(_do)


async def fetch_all(sql: str, params: tuple = ()) -> list[dict]:
    def _do():
        conn = _get_connection()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()
    return await asyncio.to_thread(_do)
