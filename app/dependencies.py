from functools import lru_cache

from app.agent import CineMystChatAgent
from app.config import Settings, get_settings
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService
from app.supabase_service import SupabaseService
from app.utils.db import DatabaseClient
from app.utils.llm_service import LLMService


@lru_cache(maxsize=1)
def get_supabase_service() -> SupabaseService:
    """Reuse one Supabase service so every request shares the same DB wrapper."""
    return SupabaseService(get_settings())


from app.guardrails import InputGuardrail, OutputGuardrail


@lru_cache(maxsize=1)
def get_input_guardrail() -> InputGuardrail:
    """Singleton input guardrail for stateful rate limiting."""
    return InputGuardrail()


@lru_cache(maxsize=1)
def get_output_guardrail() -> OutputGuardrail:
    """Singleton output guardrail."""
    return OutputGuardrail()


@lru_cache(maxsize=1)
def get_chat_agent() -> CineMystChatAgent:
    """Reuse one chat agent factory backed by the shared Supabase service and guardrails."""
    settings: Settings = get_settings()
    return CineMystChatAgent(
        settings, 
        get_supabase_service(),
        get_input_guardrail(),
        get_output_guardrail(),
    )


@lru_cache(maxsize=1)
def get_database_client() -> DatabaseClient:
    """Expose the recommendation DB helper as a singleton dependency."""
    return DatabaseClient(get_settings())


@lru_cache(maxsize=1)
def get_llm_service() -> LLMService:
    """Share one Groq helper for interest extraction."""
    return LLMService(get_settings())


@lru_cache(maxsize=1)
def get_profile_service() -> ProfileService:
    """Build the profile processing service from the shared DB and LLM helpers."""
    return ProfileService(
        db=get_database_client(),
        llm_service=get_llm_service(),
    )


@lru_cache(maxsize=1)
def get_recommendation_service() -> RecommendationService:
    """Build the recommendation service from the shared DB helper."""
    return RecommendationService(get_database_client())
