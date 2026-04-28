from __future__ import annotations

import math
from fastapi import HTTPException

from app.utils.db import DatabaseClient


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Measure how semantically similar two embedding vectors are."""
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0

    dot_product = sum(left * right for left, right in zip(vec1, vec2, strict=False))
    magnitude_1 = math.sqrt(sum(value * value for value in vec1))
    magnitude_2 = math.sqrt(sum(value * value for value in vec2))
    if magnitude_1 == 0 or magnitude_2 == 0:
        return 0.0
    return dot_product / (magnitude_1 * magnitude_2)


def normalize_scores(values: list[float]) -> list[float]:
    """Scale overlap counts into a 0..1 range so they combine cleanly with cosine similarity."""
    if not values:
        return []
    max_value = max(values)
    if max_value <= 0:
        return [0.0 for _ in values]
    return [value / max_value for value in values]


class RecommendationService:
    """Computes and stores hybrid profile recommendations."""

    def __init__(self, db: DatabaseClient) -> None:
        self.db = db

    async def generate_recommendations(self, user_id: str) -> list[dict[str, object]]:
        """Score every candidate profile, store the top 20, and return them."""
        current_user = await self.db.get_profile(user_id)
        if current_user is None:
            raise HTTPException(status_code=404, detail="Profile not found.")

        candidates = await self.db.get_candidate_profiles(user_id)
        current_embedding = current_user.get("embedding") or []
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
                    "ai_similarity": max(
                        0.0,
                        cosine_similarity(
                            current_embedding,
                            list(candidate.get("embedding") or []),
                        ),
                    ),
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
            # This keeps the semantic signal dominant while still rewarding shared interests.
            score = (
                0.6 * float(candidate["ai_similarity"])
                + 0.3 * overlap_score
                + 0.1 * ((float(candidate["role_match"]) + float(candidate["location_match"])) / 2)
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
