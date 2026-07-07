from __future__ import annotations

from fastapi import HTTPException

from app.utils.db import DatabaseClient


def normalize_scores(values: list[float]) -> list[float]:
    """Scale overlap counts into a 0..1 range so they combine cleanly with other signals."""
    if not values:
        return []
    max_value = max(values)
    if max_value <= 0:
        return [0.0 for _ in values]
    return [value / max_value for value in values]


class RecommendationService:
    """Computes and stores keyword-based profile recommendations."""

    def __init__(self, db: DatabaseClient) -> None:
        self.db = db

    async def generate_recommendations(self, user_id: str) -> list[dict[str, object]]:
        """Score every candidate profile using keyword matching, store the top 20, and return them."""
        current_user = await self.db.get_profile(user_id)
        if current_user is None:
            raise HTTPException(status_code=404, detail="Profile not found.")

        candidates = await self.db.get_candidate_profiles(user_id)
        current_interest_ids = set(current_user.get("interest_ids") or set())
        current_role = str(current_user.get("role") or "").strip().casefold()
        current_city = str(current_user.get("location_city") or "").strip().casefold()

        scored_candidates: list[dict[str, object]] = []
        overlap_counts: list[float] = []

        for candidate in candidates:
            candidate_interest_ids = set(candidate.get("interest_ids") or set())
            overlap_count = float(len(current_interest_ids & candidate_interest_ids))
            overlap_counts.append(overlap_count)

            scored_candidates.append(
                {
                    "recommended_user_id": str(candidate["id"]),
                    "interest_overlap_raw": overlap_count,
                    "role_match": 1.0
                    if current_role
                    and current_role == str(candidate.get("role") or "").strip().casefold()
                    else 0.0,
                    "location_match": 1.0
                    if current_city
                    and current_city == str(candidate.get("location_city") or "").strip().casefold()
                    else 0.0,
                }
            )

        normalized_overlap = normalize_scores(overlap_counts)
        recommendations: list[dict[str, object]] = []
        for candidate, overlap_score in zip(scored_candidates, normalized_overlap, strict=False):
            # Interest overlap is the primary signal; role and city act as secondary boosters.
            score = (
                0.6 * overlap_score
                + 0.2 * float(candidate["role_match"])
                + 0.2 * float(candidate["location_match"])
            )
            recommendations.append(
                {
                    "recommended_user_id": candidate["recommended_user_id"],
                    "score": round(score, 6),
                }
            )

        recommendations.sort(key=lambda item: float(item["score"]), reverse=True)
        top_recommendations = recommendations[:20]
        await self.db.store_recommendations(user_id, top_recommendations)
        return top_recommendations
