"""Claude AI chat integration — replaces OpenClaw."""

import json
import logging

import anthropic
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from backend.config import settings

logger = logging.getLogger("homepulse.claude")

router = APIRouter()


class ChatMessage(BaseModel):
    role: str = Field(..., max_length=20)
    content: str = Field(..., max_length=32000)

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in ("user", "assistant", "system"):
            raise ValueError("role must be user, assistant, or system")
        return v


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., max_length=100)


def _get_client():
    """Return an AsyncAnthropic client, or None if unconfigured."""
    if not settings.CLAUDE_API_KEY:
        return None
    return anthropic.AsyncAnthropic(api_key=settings.CLAUDE_API_KEY)


def _prepare_messages(messages: list[ChatMessage]):
    """Convert OpenAI-style messages to Anthropic format (extract system)."""
    system = ""
    api_messages = []
    for m in messages:
        if m.role == "system":
            system = m.content
        else:
            api_messages.append({"role": m.role, "content": m.content})
    return system, api_messages


def _build_kwargs(system: str, messages: list) -> dict:
    kwargs = {
        "model": settings.CLAUDE_MODEL,
        "max_tokens": 4096,
        "messages": messages,
    }
    if system:
        kwargs["system"] = system
    return kwargs


@router.get("/status")
async def claude_status():
    """Check if Claude API is configured."""
    if not settings.CLAUDE_API_KEY:
        return {"configured": False}
    return {"configured": True, "status": "online"}


@router.post("/chat")
async def claude_chat(request: ChatRequest):
    """Send a chat message to Claude and return the response."""
    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Claude not configured")

    try:
        system, messages = _prepare_messages(request.messages)
        response = await client.messages.create(**_build_kwargs(system, messages))
        assistant_message = response.content[0].text
        return {"response": assistant_message}

    except anthropic.AuthenticationError:
        logger.warning("Claude API authentication failed")
        raise HTTPException(status_code=401, detail="Claude API key invalid")
    except anthropic.RateLimitError:
        logger.warning("Claude API rate limited")
        raise HTTPException(status_code=429, detail="Claude API rate limited")
    except Exception:
        logger.exception("Claude chat failed")
        raise HTTPException(status_code=500, detail="Claude request failed")


@router.post("/chat/stream")
async def claude_chat_stream(request: ChatRequest):
    """Send a chat message to Claude with streaming response."""
    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Claude not configured")

    async def stream_response():
        try:
            system, messages = _prepare_messages(request.messages)
            async with client.messages.stream(**_build_kwargs(system, messages)) as stream:
                async for text in stream.text_stream:
                    # SSE format compatible with existing frontend
                    chunk = {"choices": [{"delta": {"content": text}}]}
                    yield f"data: {json.dumps(chunk)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Claude stream failed")
            yield "data: {}\n\n"

    return StreamingResponse(stream_response(), media_type="text/event-stream")
