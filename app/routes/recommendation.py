from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_database_client, get_profile_service, get_recommendation_service
from app.schemas import ProcessProfileResponse, RecommendationsResponse
from app.services.profile_service import ProfileService
from app.services.recommendation_service import RecommendationService
from app.utils.db import DatabaseClient


router = APIRouter(prefix="/v1", tags=["recommendations"])


@router.post("/process-profile/{user_id}", response_model=ProcessProfileResponse)
async def process_profile(
    user_id: str,
    profile_service: ProfileService = Depends(get_profile_service),
    recommendation_service: RecommendationService = Depends(get_recommendation_service),
) -> ProcessProfileResponse:
    """Refresh one user's embedding, mapped interests, and stored recommendations."""
    profile_result = await profile_service.process_user_profile(user_id)
    recommendations = await recommendation_service.generate_recommendations(user_id)
    return ProcessProfileResponse(
        success=True,
        user_id=user_id,
        profile_processing=profile_result,
        recommendation_count=len(recommendations),
    )


@router.get("/recommendations/{user_id}", response_model=RecommendationsResponse)
async def get_recommendations(
    user_id: str,
    db: DatabaseClient = Depends(get_database_client),
) -> RecommendationsResponse:
    """Read previously generated recommendations without recomputing them."""
    recommendations = await db.get_recommendations(user_id)
    return RecommendationsResponse(
        user_id=user_id,
        count=len(recommendations),
        recommendations=recommendations,
    )
