from __future__ import annotations

import asyncio
import json
from typing import Any

from supabase import Client, create_client

from app.config import Settings


class DatabaseClient:
    """Async-friendly Supabase helper focused on the recommendation pipeline."""

    def __init__(self, settings: Settings) -> None:
        key = settings.supabase_service_role_key or settings.supabase_key
        self.client: Client = create_client(settings.supabase_url, key)

    async def get_profile(self, user_id: str) -> dict[str, Any] | None:
        """Load one profile together with its already stored interest IDs."""
        rows = await self._execute_rows(
            self.client.table("profiles")
            .select("id, role, bio, location_city, embedding")
            .eq("id", user_id)
            .limit(1)
        )
        if not rows:
            return None
        profile = rows[0]
        profile["embedding"] = self._parse_embedding(profile.get("embedding"))
        profile["interest_ids"] = await self.get_user_interest_ids(user_id)
        return profile

    async def update_embedding(self, user_id: str, embedding: list[float]) -> None:
        """Persist the latest embedding back to the `profiles` table."""
        await self._run(
            self.client.table("profiles")
            .update({"embedding": embedding})
            .eq("id", user_id)
            .execute
        )

    async def get_all_interests(self) -> list[dict[str, Any]]:
        """Return the allowed interest taxonomy that AI output must be validated against."""
        rows = await self._execute_rows(
            self.client.table("interests")
            .select("id, name")
            .order("name")
        )
        return rows

    async def clear_user_interests(self, user_id: str) -> None:
        """Remove old interest mappings before replacing them with refreshed ones."""
        await self._run(
            self.client.table("user_interests")
            .delete()
            .eq("user_id", user_id)
            .execute
        )

    async def insert_user_interests(self, user_id: str, interest_ids: list[str]) -> None:
        """Insert the validated interest IDs selected for a user profile."""
        if not interest_ids:
            return
        payload = [{"user_id": user_id, "interest_id": interest_id} for interest_id in interest_ids]
        await self._run(self.client.table("user_interests").insert(payload).execute)

    async def get_user_interest_ids(self, user_id: str) -> set[str]:
        """Read the user's interest IDs as a set for fast overlap checks."""
        rows = await self._execute_rows(
            self.client.table("user_interests")
            .select("interest_id")
            .eq("user_id", user_id)
        )
        return {
            str(row["interest_id"])
            for row in rows
            if isinstance(row, dict) and row.get("interest_id") is not None
        }

    async def get_candidate_profiles(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch all other profiles plus their interest IDs for recommendation scoring."""
        profile_rows = await self._execute_rows(
            self.client.table("profiles")
            .select("id, role, bio, location_city, embedding")
            .neq("id", user_id)
        )
        if not profile_rows:
            return []

        candidate_ids = [
            str(row["id"])
            for row in profile_rows
            if isinstance(row, dict) and row.get("id") is not None
        ]
        interest_map = await self._get_interest_map(candidate_ids)

        candidates: list[dict[str, Any]] = []
        for row in profile_rows:
            candidate_id = str(row.get("id") or "")
            if not candidate_id:
                continue
            candidates.append(
                {
                    "id": candidate_id,
                    "role": row.get("role"),
                    "bio": row.get("bio"),
                    "location_city": row.get("location_city"),
                    "embedding": self._parse_embedding(row.get("embedding")),
                    "interest_ids": interest_map.get(candidate_id, set()),
                }
            )
        return candidates

    async def store_recommendations(self, user_id: str, recommendations: list[dict[str, Any]]) -> None:
        """Replace a user's stored recommendations with the latest top-ranked results."""
        await self._run(
            self.client.table("user_recommendations")
            .delete()
            .eq("user_id", user_id)
            .execute
        )

        if not recommendations:
            return

        payload = [
            {
                "user_id": user_id,
                "recommended_user_id": recommendation["recommended_user_id"],
                "score": recommendation["score"],
            }
            for recommendation in recommendations
        ]
        await self._run(self.client.table("user_recommendations").insert(payload).execute)

    async def get_recommendations(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return saved recommendations with lightweight profile data for the client."""
        rows = await self._execute_rows(
            self.client.table("user_recommendations")
            .select("user_id, recommended_user_id, score")
            .eq("user_id", user_id)
            .order("score", desc=True)
            .limit(limit)
        )
        if not rows:
            return []

        recommended_ids = [
            str(row["recommended_user_id"])
            for row in rows
            if isinstance(row, dict) and row.get("recommended_user_id") is not None
        ]
        profiles = await self._execute_rows(
            self.client.table("profiles")
            .select("id, role, bio, location_city")
            .in_("id", recommended_ids)
        ) if recommended_ids else []
        profile_map = {
            str(profile["id"]): profile
            for profile in profiles
            if isinstance(profile, dict) and profile.get("id") is not None
        }

        recommendations: list[dict[str, Any]] = []
        for row in rows:
            recommended_user_id = str(row.get("recommended_user_id") or "")
            if not recommended_user_id:
                continue
            recommendations.append(
                {
                    "recommended_user_id": recommended_user_id,
                    "score": float(row.get("score") or 0),
                    "profile": profile_map.get(recommended_user_id, {}),
                }
            )
        return recommendations

    async def _get_interest_map(self, user_ids: list[str]) -> dict[str, set[str]]:
        """Group `user_interests` rows by user so scoring can compare interest overlap quickly."""
        if not user_ids:
            return {}

        rows = await self._execute_rows(
            self.client.table("user_interests")
            .select("user_id, interest_id")
            .in_("user_id", user_ids)
        )
        interest_map: dict[str, set[str]] = {user_id: set() for user_id in user_ids}
        for row in rows:
            user_id = str(row.get("user_id") or "")
            interest_id = row.get("interest_id")
            if user_id and interest_id is not None:
                interest_map.setdefault(user_id, set()).add(str(interest_id))
        return interest_map

    async def _execute_rows(self, query: Any) -> list[dict[str, Any]]:
        """Run a Supabase request and normalize the response payload to a list of dict rows."""
        response = await self._run(query.execute)
        return self._extract_rows(getattr(response, "data", None))

    async def _run(self, fn: Any) -> Any:
        """Offload the sync Supabase client call to a worker thread for async endpoints."""
        return await asyncio.to_thread(fn)

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
        """Handle the few payload shapes Supabase/PostgREST can return in practice."""
        if payload is None:
            return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            candidate_keys = ("data", "rows", "result", "payload")
            for key in candidate_keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
            return []
        return []

    def _parse_embedding(self, raw_embedding: Any) -> list[float]:
        """Parse pgvector values whether they come back as lists or serialized strings."""
        if raw_embedding is None:
            return []
        if isinstance(raw_embedding, list):
            return [float(value) for value in raw_embedding]
        if isinstance(raw_embedding, str):
            stripped = raw_embedding.strip()
            if not stripped:
                return []
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return [float(value) for value in parsed]
            except json.JSONDecodeError:
                pass

            if stripped.startswith("[") and stripped.endswith("]"):
                stripped = stripped[1:-1]
            parts = [part.strip() for part in stripped.split(",") if part.strip()]
            try:
                return [float(part) for part in parts]
            except ValueError:
                return []
        return []
