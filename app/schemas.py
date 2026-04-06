from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(description="The CineMyst profiles.id for the current user.")
    message: str = Field(description="The user's natural language query.")
    conversation_id: str | None = Field(
        default=None,
        description="Optional persistent thread identifier for LangGraph memory.",
    )


class ChatResponse(BaseModel):
    answer: str
    user_id: str
    conversation_id: str
    profile_summary: str


class UserContextResponse(BaseModel):
    user_id: str
    profile: dict
    bookings: list[dict]


class ConversationSummary(BaseModel):
    conversation_id: str
    user_id: str
    title: str
    last_message_preview: str
    last_message_at: str | None = None
    created_at: str | None = None


class ConversationMessage(BaseModel):
    message_id: str | None = None
    conversation_id: str
    user_id: str
    role: str
    content: str
    created_at: str | None = None


class ConversationListResponse(BaseModel):
    user_id: str
    conversations: list[ConversationSummary]


class ConversationMessagesResponse(BaseModel):
    user_id: str
    conversation_id: str
    messages: list[ConversationMessage]
