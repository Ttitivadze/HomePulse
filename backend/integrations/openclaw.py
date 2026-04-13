import logging

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.config import settings
from backend.integrations.arr import _get_client as _get_shared_client

logger = logging.getLogger("homelab.openclaw")

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.get("/status")
async def openclaw_status():
    """Check if OpenClaw is reachable."""
    if not settings.OPENCLAW_URL:
        return {"configured": False}

    try:
        client = await _get_shared_client()
        resp = await client.get(
            f"{settings.OPENCLAW_URL}/api/models",
            headers={"Authorization": f"Bearer {settings.OPENCLAW_API_KEY}"},
            timeout=5.0,
        )
        if resp.status_code == 200:
            models = resp.json()
            return {"configured": True, "status": "online", "models": models}
        return {"configured": True, "status": "error"}
    except httpx.ConnectError:
        return {"configured": True, "status": "offline"}
    except Exception:
        return {"configured": True, "status": "error"}


@router.post("/chat")
async def openclaw_chat(request: ChatRequest):
    """Send a chat message to OpenClaw and return the response."""
    if not settings.OPENCLAW_URL:
        raise HTTPException(status_code=503, detail="OpenClaw not configured")

    try:
        payload = {
            "model": settings.OPENCLAW_MODEL,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
        }

        client = await _get_shared_client()
        resp = await client.post(
            f"{settings.OPENCLAW_URL}/api/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENCLAW_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120.0,
        )
        resp.raise_for_status()
        data = resp.json()

        assistant_message = data["choices"][0]["message"]["content"]
        return {"response": assistant_message}

    except httpx.ConnectError:
        logger.warning("Cannot connect to OpenClaw at %s", settings.OPENCLAW_URL)
        raise HTTPException(status_code=503, detail="Cannot connect to OpenClaw")
    except httpx.HTTPStatusError as e:
        logger.warning("OpenClaw API error: %s", e.response.status_code)
        raise HTTPException(
            status_code=e.response.status_code, detail="OpenClaw API error"
        )
    except Exception as e:
        logger.exception("OpenClaw chat failed")
        raise HTTPException(status_code=500, detail="OpenClaw request failed")


@router.post("/chat/stream")
async def openclaw_chat_stream(request: ChatRequest):
    """Send a chat message to OpenClaw with streaming response."""
    if not settings.OPENCLAW_URL:
        raise HTTPException(status_code=503, detail="OpenClaw not configured")

    async def stream_response():
        payload = {
            "model": settings.OPENCLAW_MODEL,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
        }

        client = await _get_shared_client()
        async with client.stream(
            "POST",
            f"{settings.OPENCLAW_URL}/api/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENCLAW_API_KEY}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120.0,
        ) as resp:
            async for chunk in resp.aiter_text():
                yield chunk

    return StreamingResponse(stream_response(), media_type="text/event-stream")
