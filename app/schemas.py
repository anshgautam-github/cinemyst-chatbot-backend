from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for both standard and streaming chat endpoints."""
    user_id: str = Field(description="The CineMyst profiles.id for the current user.")
    message: str = Field(description="The user's natural language query.")
    conversation_id: str | None = Field(
        default=None,
        description="Optional persistent thread identifier for LangGraph memory.",
    )


class ChatResponse(BaseModel):
    """Full chat response returned by the non-streaming endpoint."""
    answer: str
    user_id: str
    conversation_id: str
    profile_summary: str


class CastingDraftRequest(BaseModel):
    """Request body for generating a structured casting-post draft."""
    user_id: str = Field(description="The CineMyst profiles.id for the current user.")
    rough_idea: str = Field(default="", description="The rough role idea typed by the user.")
    context: str = Field(
        default="",
        description="Existing form context flattened into plain text.",
    )


class CastingDraftResponse(BaseModel):
    """Structured casting-post draft returned to the iOS job-posting flow."""
    project_title: str | None = None
    project_type: str | None = None
    character_name: str | None = None
    character_description: str | None = None
    age_range: str | None = None
    gender: str | None = None
    position: str | None = None
    genre: str | None = None


class UserContextResponse(BaseModel):
    """Profile snapshot plus recent bookings shown around the chat UI."""
    user_id: str
    profile: dict
    bookings: list[dict]


class ConversationSummary(BaseModel):
    """Small conversation card shown in a conversation list view."""
    conversation_id: str
    user_id: str
    title: str
    last_message_preview: str
    last_message_at: str | None = None
    created_at: str | None = None


class ConversationMessage(BaseModel):
    """One stored chat message."""
    message_id: str | None = None
    conversation_id: str
    user_id: str
    role: str
    content: str
    created_at: str | None = None


class ConversationListResponse(BaseModel):
    """Conversation list API response."""
    user_id: str
    conversations: list[ConversationSummary]


class ConversationMessagesResponse(BaseModel):
    """Conversation detail API response."""
    user_id: str
    conversation_id: str
    messages: list[ConversationMessage]


class ProfileProcessingResult(BaseModel):
    """Summary of what happened during profile embedding and interest processing."""
    user_id: str
    embedding_dimensions: int
    interest_count: int
    interests: list[str]


class ProcessProfileResponse(BaseModel):
    """Response returned after refreshing one user's profile intelligence."""
    success: bool
    user_id: str
    profile_processing: ProfileProcessingResult
    recommendation_count: int


class RecommendationItem(BaseModel):
    """One recommended profile with its score and lightweight profile payload."""
    recommended_user_id: str
    score: float
    profile: dict


class RecommendationsResponse(BaseModel):
    """Recommendation list API response."""
    user_id: str
    count: int
    recommendations: list[RecommendationItem]
