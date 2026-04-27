from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from .agent import CineMystChatAgent
from .config import get_settings
from .routes.recommendation import router as recommendation_router
from .schemas import (
    ChatRequest,
    ChatResponse,
    ConversationListResponse,
    ConversationMessagesResponse,
    UserContextResponse,
)
from .supabase_service import SupabaseService


settings = get_settings()
supabase_service = SupabaseService(settings)
chat_agent = CineMystChatAgent(settings, supabase_service)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


app = FastAPI(
    title="CineMyst Chatbot Backend",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(recommendation_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "environment": settings.app_env}


@app.get("/v1/users/{user_id}/context", response_model=UserContextResponse)
async def get_user_context(user_id: str) -> UserContextResponse:
    profile = supabase_service.get_user_profile(user_id)
    bookings = supabase_service.get_user_bookings(user_id, limit=5)
    return UserContextResponse(user_id=user_id, profile=profile, bookings=bookings)


@app.get("/v1/users/{user_id}/conversations", response_model=ConversationListResponse)
async def list_conversations(user_id: str) -> ConversationListResponse:
    conversations = supabase_service.list_conversations(user_id=user_id, limit=20)
    return ConversationListResponse(user_id=user_id, conversations=conversations)


@app.get(
    "/v1/users/{user_id}/conversations/{conversation_id}/messages",
    response_model=ConversationMessagesResponse,
)
async def get_conversation_messages(user_id: str, conversation_id: str) -> ConversationMessagesResponse:
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


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    conversation_id = request.conversation_id or f"user-{request.user_id}"
    answer, profile_summary = chat_agent.chat(
        user_id=request.user_id,
        message=request.message,
        conversation_id=conversation_id,
    )
    return ChatResponse(
        answer=answer,
        user_id=request.user_id,
        conversation_id=conversation_id,
        profile_summary=profile_summary,
    )


@app.post("/v1/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="message cannot be empty")

    conversation_id = request.conversation_id or f"user-{request.user_id}"

    async def event_stream():
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
