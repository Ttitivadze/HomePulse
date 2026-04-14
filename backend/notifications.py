"""Notification framework with Telegram support."""

import logging

import httpx
from fastapi import APIRouter, HTTPException

from backend.config import settings

logger = logging.getLogger("homepulse.notifications")

router = APIRouter()


async def send_telegram(title: str, message: str, level: str = "info") -> bool:
    """Send a notification via Telegram Bot API."""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return False

    emoji = {"info": "ℹ️", "warning": "⚠️", "error": "🔴", "success": "✅"}.get(level, "ℹ️")
    text = f"{emoji} *{title}*\n{message}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id": settings.TELEGRAM_CHAT_ID,
                    "text": text,
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code == 200:
                return True
            logger.warning("Telegram API returned %d: %s", resp.status_code, resp.text)
            return False
    except Exception:
        logger.exception("Telegram notification failed")
        return False


async def send_notification(title: str, message: str, level: str = "info") -> bool:
    """Send a notification via all configured providers."""
    sent = False
    if settings.TELEGRAM_BOT_TOKEN:
        sent = await send_telegram(title, message, level) or sent
    return sent


@router.post("/test")
async def test_notification():
    """Send a test notification to verify configuration."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(status_code=400, detail="No notification providers configured (set TELEGRAM_BOT_TOKEN)")

    success = await send_notification(
        "HomePulse Test",
        "This is a test notification from HomePulse. If you see this, notifications are working!",
        level="success",
    )
    if success:
        return {"status": "sent", "message": "Test notification sent successfully"}
    raise HTTPException(status_code=500, detail="Failed to send notification — check bot token and chat ID")
