from functools import lru_cache

from app.agent import CineMystChatAgent
from app.config import Settings, get_settings
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService
from app.supabase_service import SupabaseService
from app.utils.db import DatabaseClient
from app.utils.openai_service import OpenAIService


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    """Reuse one Supabase service so every request shares the same DB wrapper."""
    return SupabaseService(get_settings())


@lru_cache(maxsize=1)
def get_chat_agent() -> CineMystChatAgent:
    """Reuse one chat agent factory backed by the shared Supabase service."""
    settings: Settings = get_settings()
    return CineMystChatAgent(settings, get_supabase_service())


@lru_cache(maxsize=1)
def get_database_client() -> DatabaseClient:
    """Expose the recommendation DB helper as a singleton dependency."""
    return DatabaseClient(get_settings())


@lru_cache(maxsize=1)
def get_openai_service() -> OpenAIService:
    """Share one OpenAI helper for embeddings and interest extraction."""
    return OpenAIService(get_settings())


@lru_cache(maxsize=1)
def get_profile_service() -> ProfileService:
    """Build the profile processing service from the shared DB and OpenAI helpers."""
    return ProfileService(
        db=get_database_client(),
        openai_service=get_openai_service(),
    )


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    """Build the recommendation service from the shared DB helper."""
    return RecommendationService(get_database_client())
