from __future__ import annotations

from fastapi import HTTPException

from app.utils.db import DatabaseClient
from app.utils.openai_service import OpenAIService


class ProfileService:
    def __init__(self, db: DatabaseClient, openai_service: OpenAIService) -> None:
        self.db = db
        self.openai_service = openai_service

    async def process_user_profile(self, user_id: str) -> dict[str, object]:
        profile = await self.db.get_profile(user_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Profile not found.")

        profile_text = self._build_profile_text(profile)
        embedding = await self.openai_service.generate_embedding(profile_text)
        await self.db.update_embedding(user_id, embedding)

        interests = await self.db.get_all_interests()
        interest_name_map = {
            str(interest["name"]).strip().casefold(): {
                "id": str(interest["id"]),
                "name": str(interest["name"]).strip(),
            }
            for interest in interests
            if interest.get("id") is not None and interest.get("name")
        }
        interest_names = [item["name"] for item in interest_name_map.values()]

        extracted_names = await self.openai_service.extract_interests(
            bio=profile_text,
            interest_list=interest_names,
        )
        valid_interest_ids: list[str] = []
        valid_interest_names: list[str] = []
        seen_interest_ids: set[str] = set()
        for interest_name in extracted_names:
            match = interest_name_map.get(interest_name.strip().casefold())
            if match is None:
                continue
            interest_id = match["id"]
            if interest_id in seen_interest_ids:
                continue
            seen_interest_ids.add(interest_id)
            valid_interest_ids.append(interest_id)
            valid_interest_names.append(match["name"])

        await self.db.clear_user_interests(user_id)
        await self.db.insert_user_interests(user_id, valid_interest_ids)

        return {
            "user_id": user_id,
            "embedding_dimensions": len(embedding),
            "interest_count": len(valid_interest_ids),
            "interests": valid_interest_names,
        }

    def _build_profile_text(self, profile: dict[str, object]) -> str:
        parts = [
            str(profile.get("role") or "").strip(),
            str(profile.get("bio") or "").strip(),
            str(profile.get("location_city") or "").strip(),
        ]
        return " | ".join(part for part in parts if part)
