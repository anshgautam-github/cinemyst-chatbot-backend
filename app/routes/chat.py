from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.agent import CineMystChatAgent
from app.dependencies import get_chat_agent, get_supabase_service
from app.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    UserContextResponse,
)
from app.supabase_service import SupabaseService


router = APIRouter(prefix="/v1", tags=["chat"])
logger = logging.getLogger(__name__)

CHAT_FALLBACK_ANSWER = (
    "I couldn't complete that request right now, but the CineMyst AI service is online. "
    "Please try again in a moment."
)
GREETING_FALLBACK_ANSWER = (
    "Hi, I'm here. Ask me about CineMyst mentors, jobs, pricing, availability, "
    "or what fits your profile best."
)
GREETING_MESSAGES = {
    "hello",
    "hello how are u",
    "hello how are you",
    "hey",
    "hi",
    "hii",
    "yo",
}


def fallback_answer_for(message: str) -> str:
    """Return a user-friendly fallback when the AI provider fails."""
    normalized_message = " ".join(message.lower().strip().split())
    if normalized_message in GREETING_MESSAGES:
        return GREETING_FALLBACK_ANSWER
    return CHAT_FALLBACK_ANSWER


@router.get("/users/{user_id}/context", response_model=UserContextResponse)
async def get_user_context(
    user_id: str,
    supabase_service: SupabaseService = Depends(get_supabase_service),
) -> UserContextResponse:
    """Return the profile snapshot the app can show alongside the chat experience."""
    profile = supabase_service.get_user_profile(user_id)
    bookings = supabase_service.get_user_bookings(user_id, limit=5)
    return UserContextResponse(user_id=user_id, profile=profile, bookings=bookings)


@router.get("/users/{user_id}/conversations", response_model=ConversationListResponse)
async def list_conversations(
    user_id: str,
    supabase_service: SupabaseService = Depends(get_supabase_service),
) -> ConversationListResponse:
    """List saved chat threads so the app can reopen prior conversations."""
    conversations = supabase_service.list_conversations(user_id=user_id, limit=20)
    return ConversationListResponse(user_id=user_id, conversations=conversations)


@router.get(
    "/users/{user_id}/conversations/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def get_conversation_messages(
    user_id: str,
    conversation_id: str,
    supabase_service: SupabaseService = Depends(get_supabase_service),
) -> ConversationMessagesResponse:
    """Return the ordered message history for one saved conversation."""
    messages = supabase_service.get_conversation_messages(
        user_id=user_id,
        conversation_id=conversation_id,
        limit=100,
    )
    return ConversationMessagesResponse(
        user_id=user_id,
        conversation_id=conversation_id,
        messages=messages,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_agent: CineMystChatAgent = Depends(get_chat_agent),
) -> ChatResponse:
    """Handle the non-streaming chat flow used when the client wants a full response body."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    conversation_id = request.conversation_id or f"user-{request.user_id}"
    try:
        answer, profile_summary = chat_agent.chat(
            user_id=request.user_id,
            message=request.message,
            conversation_id=conversation_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Chat request failed")
        answer = fallback_answer_for(request.message)
        profile_summary = ""
    return ChatResponse(
        answer=answer,
        user_id=request.user_id,
        conversation_id=conversation_id,
        profile_summary=profile_summary,
    )


@router.post("/chat/stream")
async def stream_chat(
    request: ChatRequest,
    chat_agent: CineMystChatAgent = Depends(get_chat_agent),
) -> StreamingResponse:
    """Stream incremental assistant tokens back to the iOS client over SSE."""
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    conversation_id = request.conversation_id or f"user-{request.user_id}"

    async def event_stream() -> AsyncIterator[str]:
        """Wrap the agent stream into SSE `data:` events that the app can consume."""
        try:
            async for delta in chat_agent.stream_chat(
                user_id=request.user_id,
                message=request.message,
                conversation_id=conversation_id,
            ):
                payload = {"delta": delta}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: {\"done\": true}\n\n"
        except Exception as error:  # noqa: BLE001
            payload = {"error": str(error)}
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            yield "data: {\"done\": true}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
