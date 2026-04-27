from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService
from app.utils.db import DatabaseClient
from app.utils.openai_service import OpenAIService


router = APIRouter(prefix="/v1", tags=["recommendations"])

settings = get_settings()
db = DatabaseClient(settings)
openai_service = OpenAIService(settings)
profile_service = ProfileService(db=db, openai_service=openai_service)
recommendation_service = RecommendationService(db=db)


@router.post("/process-profile/{user_id}")
async def process_profile(user_id: str) -> dict[str, object]:
    profile_result = await profile_service.process_user_profile(user_id)
    recommendations = await recommendation_service.generate_recommendations(user_id)
    return {
        "success": True,
        "user_id": user_id,
        "profile_processing": profile_result,
        "recommendation_count": len(recommendations),
    }


@router.get("/recommendations/{user_id}")
async def get_recommendations(user_id: str) -> dict[str, object]:
    recommendations = await db.get_recommendations(user_id)
    return {
        "user_id": user_id,
        "count": len(recommendations),
        "recommendations": recommendations,
    }
