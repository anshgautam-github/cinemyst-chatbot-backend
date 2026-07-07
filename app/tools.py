from __future__ import annotations

import json

from langchain_core.tools import tool

from .supabase_service import SupabaseService
from .utils.cache import ttl_cache


def build_tools(service: SupabaseService):
    """Expose a curated, safe tool surface to the LLM instead of raw database access."""
    @tool
    def get_user_profile(user_id: str) -> str:
        """Return the CineMyst user profile for the given profiles.id."""
        return json.dumps(service.get_user_profile(user_id), ensure_ascii=False)

    @tool
    def get_user_bookings(user_id: str, limit: int = 5) -> str:
        """Return the user's mentorship bookings with mentor details."""
        return json.dumps(service.get_user_bookings(user_id, limit), ensure_ascii=False)

    @tool
    @ttl_cache(ttl_seconds=300)
    def search_mentors(
        role: str = "",
        specialty: str = "",
        max_price: int = 0,
        min_rating: float = 0,
        limit: int = 5,
    ) -> str:
        """Search CineMyst mentors by role, specialty, budget, and minimum rating."""
        return json.dumps(
            service.search_mentors(
                role=role or None,
                specialty=specialty or None,
                max_price=max_price or None,
                min_rating=min_rating or None,
                limit=limit,
            ),
            ensure_ascii=False,
        )

    @tool
    @ttl_cache(ttl_seconds=300)
    def get_mentor_details(mentor_name: str = "", mentor_id: str = "") -> str:
        """Get a detailed mentor profile by mentor name or mentor_profiles.id."""
        return json.dumps(
            service.get_mentor_details(
                mentor_name=mentor_name or None,
                mentor_id=mentor_id or None,
            ),
            ensure_ascii=False,
        )

    @tool
    def get_mentor_availability(mentor_id: str, limit: int = 8) -> str:
        """Return upcoming available mentorship slots for a given mentor profile id."""
        return json.dumps(service.get_mentor_availability(mentor_id, limit), ensure_ascii=False)

    @tool
    @ttl_cache(ttl_seconds=300)
    def search_jobs(
        role: str = "",
        location: str = "",
        keywords: str = "",
        max_rate_per_day: int = 0,
        limit: int = 5,
    ) -> str:
        """Search CineMyst jobs by role, location, keywords, and budget."""
        return json.dumps(
            service.search_jobs(
                role=role or None,
                location=location or None,
                keywords=keywords or None,
                max_rate_per_day=max_rate_per_day or None,
                limit=limit,
            ),
            ensure_ascii=False,
        )

    @tool
    @ttl_cache(ttl_seconds=300)
    def recommend_mentors_for_user(user_id: str, limit: int = 4) -> str:
        """Recommend mentors personalized for the given CineMyst user id."""
        return json.dumps(service.recommend_mentors_for_user(user_id, limit), ensure_ascii=False)

    return [
        get_user_profile,
        get_user_bookings,
        search_mentors,
        get_mentor_details,
        get_mentor_availability,
        search_jobs,
        recommend_mentors_for_user,
    ]
