from __future__ import annotations

import json
from typing import Any

from supabase import Client, create_client

from .config import Settings


class SupabaseService:
    def __init__(self, settings: Settings) -> None:
        key = settings.supabase_service_role_key or settings.supabase_key
        self.client: Client = create_client(settings.supabase_url, key)
        self.settings = settings

    def _extract_rows(self, payload: Any) -> list[dict[str, Any]]:
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
        if isinstance(payload, (bytes, bytearray)):
            return self._extract_rows(json.loads(payload))
        if isinstance(payload, str):
            try:
                return self._extract_rows(json.loads(payload))
            except json.JSONDecodeError:
                return []
        return []

    def _execute_rows(self, query: Any) -> list[dict[str, Any]]:
        response = query.execute()
        return self._extract_rows(getattr(response, "data", None))

    def _parse_metadata(self, metadata: Any) -> dict[str, Any]:
        if metadata is None:
            return {}
        if isinstance(metadata, dict):
            return metadata
        if isinstance(metadata, str):
            try:
                parsed = json.loads(metadata)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                return {}
        return {}

    def _extract_price_map(self, metadata: dict[str, Any]) -> dict[str, int]:
        raw_prices = metadata.get("prices_json")
        if isinstance(raw_prices, str):
            try:
                raw_prices = json.loads(raw_prices)
            except json.JSONDecodeError:
                raw_prices = {}
        if not isinstance(raw_prices, dict):
            return {}

        parsed: dict[str, int] = {}
        for key, value in raw_prices.items():
            if value is None:
                continue
            numeric: int | None = None
            if isinstance(value, (int, float)):
                numeric = int(value)
            elif isinstance(value, str):
                cleaned = value.lower().replace("₹", "").replace(",", "").replace("/hour", "").strip()
                if cleaned.endswith("k"):
                    try:
                        numeric = int(float(cleaned[:-1]) * 1000)
                    except ValueError:
                        numeric = None
                else:
                    try:
                        numeric = int(float(cleaned))
                    except ValueError:
                        numeric = None
            if numeric is not None:
                parsed[str(key)] = numeric
        return parsed

    def _mentor_to_result(self, row: dict[str, Any]) -> dict[str, Any]:
        metadata = self._parse_metadata(row.get("metadata"))
        price_map = self._extract_price_map(metadata)
        raw_areas = row.get("mentorship_areas") or []
        if isinstance(raw_areas, str):
            try:
                raw_areas = json.loads(raw_areas)
            except json.JSONDecodeError:
                raw_areas = [raw_areas]
        if not isinstance(raw_areas, list):
            raw_areas = []

        money = row.get("money")
        if isinstance(money, str):
            try:
                money = int(float(money))
            except ValueError:
                money = None
        if isinstance(money, float):
            money = int(money)

        derived_min_price = min(price_map.values()) if price_map else money

        return {
            "mentor_id": row.get("id"),
            "user_id": row.get("user_id"),
            "name": row.get("display_name") or row.get("name") or "Unknown",
            "headline": row.get("role"),
            "about": row.get("about"),
            "rating": float(row.get("rating") or 0),
            "rating_count": int(row.get("rating_count") or 0),
            "years_experience": row.get("yoe"),
            "session_count": row.get("session"),
            "profile_picture_url": row.get("profile_picture_url"),
            "specialties": [str(area) for area in raw_areas],
            "price_map": price_map,
            "starting_price_inr": derived_min_price,
            "metadata": metadata,
        }

    def _job_to_result(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "job_id": row.get("id"),
            "title": row.get("title"),
            "company_name": row.get("company_name"),
            "location": row.get("location"),
            "rate_per_day": row.get("rate_per_day"),
            "job_type": row.get("job_type"),
            "status": row.get("status"),
            "description": row.get("description"),
            "requirements": row.get("requirements"),
            "application_deadline": row.get("application_deadline"),
        }

    def _conversation_title(self, text: str) -> str:
        cleaned = " ".join((text or "").strip().split())
        if not cleaned:
            return "New chat"
        return cleaned[:57] + "..." if len(cleaned) > 60 else cleaned

    def _message_preview(self, text: str) -> str:
        cleaned = " ".join((text or "").strip().split())
        return cleaned[:117] + "..." if len(cleaned) > 120 else cleaned

    def get_user_profile(self, user_id: str) -> dict[str, Any]:
        rows = self._execute_rows(
            self.client.table("profiles")
            .select("id, username, full_name, role, location_state, location_city, avatar_url, bio, employment_status")
            .eq("id", user_id)
            .limit(1)
        )
        return rows[0] if rows else {"id": user_id}

    def ensure_conversation(self, user_id: str, conversation_id: str, seed_message: str | None = None) -> dict[str, Any]:
        existing = self._execute_rows(
            self.client.table("chat_conversations")
            .select("conversation_id, user_id, title, last_message_preview, last_message_at, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .limit(1)
        )
        if existing:
            return existing[0]

        payload = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "title": self._conversation_title(seed_message or ""),
            "last_message_preview": self._message_preview(seed_message or ""),
        }
        created = self._execute_rows(
            self.client.table("chat_conversations")
            .insert(payload)
            .select("conversation_id, user_id, title, last_message_preview, last_message_at, created_at")
        )
        return created[0] if created else payload

    def save_conversation_message(
        self,
        *,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
    ) -> dict[str, Any]:
        payload = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
        }
        created = self._execute_rows(
            self.client.table("chat_messages")
            .insert(payload)
            .select("id, conversation_id, user_id, role, content, created_at")
        )

        update_payload = {
            "last_message_preview": self._message_preview(content),
        }
        if role == "user":
            existing = self._execute_rows(
                self.client.table("chat_conversations")
                .select("title")
                .eq("conversation_id", conversation_id)
                .eq("user_id", user_id)
                .limit(1)
            )
            current_title = (existing[0].get("title") if existing else "") or ""
            if not current_title or current_title == "New chat":
                update_payload["title"] = self._conversation_title(content)

        self.client.table("chat_conversations").update(update_payload).eq("conversation_id", conversation_id).eq(
            "user_id", user_id
        ).execute()

        return created[0] if created else payload

    def list_conversations(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._execute_rows(
            self.client.table("chat_conversations")
            .select("conversation_id, user_id, title, last_message_preview, last_message_at, created_at")
            .eq("user_id", user_id)
            .order("last_message_at", desc=True)
            .limit(limit)
        )
        return [
            {
                "conversation_id": row.get("conversation_id"),
                "user_id": row.get("user_id"),
                "title": row.get("title") or "New chat",
                "last_message_preview": row.get("last_message_preview") or "",
                "last_message_at": row.get("last_message_at"),
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]

    def get_conversation_messages(
        self,
        user_id: str,
        conversation_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = self._execute_rows(
            self.client.table("chat_messages")
            .select("id, conversation_id, user_id, role, content, created_at")
            .eq("conversation_id", conversation_id)
            .eq("user_id", user_id)
            .order("created_at", desc=False)
            .limit(limit)
        )
        return [
            {
                "message_id": row.get("id"),
                "conversation_id": row.get("conversation_id"),
                "user_id": row.get("user_id"),
                "role": row.get("role"),
                "content": row.get("content") or "",
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]

    def get_user_bookings(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        result_limit = limit or self.settings.default_results_limit
        rows = self._execute_rows(
            self.client.table("mentorship_sessions")
            .select("id, mentor_id, mentee_id, scheduled_at, duration_minutes, status, price_cents, currency, slot_id")
            .eq("mentee_id", user_id)
            .order("scheduled_at", desc=False)
            .limit(result_limit)
        )
        mentor_ids = [row["mentor_id"] for row in rows if row.get("mentor_id")]
        mentor_map: dict[str, dict[str, Any]] = {}
        if mentor_ids:
            mentor_rows = self._execute_rows(
                self.client.table("mentor_profiles")
                .select("id, display_name, role, profile_picture_url, mentorship_areas")
                .in_("id", mentor_ids)
            )
            mentor_map = {row["id"]: row for row in mentor_rows if row.get("id")}

        bookings: list[dict[str, Any]] = []
        for row in rows:
            mentor = mentor_map.get(row.get("mentor_id"), {})
            raw_areas = mentor.get("mentorship_areas") or []
            if isinstance(raw_areas, str):
                try:
                    raw_areas = json.loads(raw_areas)
                except json.JSONDecodeError:
                    raw_areas = [raw_areas]
            if not isinstance(raw_areas, list):
                raw_areas = []
            bookings.append(
                {
                    "booking_id": row.get("id"),
                    "status": row.get("status"),
                    "scheduled_at": row.get("scheduled_at"),
                    "duration_minutes": row.get("duration_minutes"),
                    "price_cents": row.get("price_cents"),
                    "currency": row.get("currency"),
                    "mentor_id": row.get("mentor_id"),
                    "mentor_name": mentor.get("display_name") or "Unknown mentor",
                    "mentor_role": mentor.get("role"),
                    "mentor_image_url": mentor.get("profile_picture_url"),
                    "mentor_specialties": [str(area) for area in raw_areas],
                }
            )
        return bookings

    def search_mentors(
        self,
        role: str | None = None,
        specialty: str | None = None,
        max_price: int | None = None,
        min_rating: float | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        result_limit = limit or self.settings.mentor_results_limit
        rows = self._execute_rows(
            self.client.table("mentor_profiles")
            .select("id, user_id, display_name, name, role, about, mentorship_areas, rating, rating_count, profile_picture_url, metadata, yoe, session, money")
            .order("rating", desc=True)
            .limit(max(result_limit * 4, 20))
        )

        candidates = [self._mentor_to_result(row) for row in rows]

        if role:
            role_lower = role.lower()
            candidates = [
                item for item in candidates if role_lower in str(item.get("headline") or "").lower()
            ]
        if specialty:
            specialty_lower = specialty.lower()
            candidates = [
                item
                for item in candidates
                if any(specialty_lower in area.lower() for area in item.get("specialties", []))
            ]
        if min_rating is not None and min_rating > 0:
            candidates = [item for item in candidates if float(item.get("rating") or 0) >= min_rating]
        if max_price is not None and max_price > 0:
            candidates = [
                item
                for item in candidates
                if item.get("starting_price_inr") is not None
                and int(item["starting_price_inr"]) <= max_price
            ]

        return candidates[:result_limit]

    def get_mentor_details(self, mentor_name: str | None = None, mentor_id: str | None = None) -> dict[str, Any]:
        if mentor_id:
            rows = self._execute_rows(
                self.client.table("mentor_profiles")
                .select("id, user_id, display_name, name, role, about, mentorship_areas, rating, rating_count, profile_picture_url, metadata, yoe, session, money")
                .eq("id", mentor_id)
                .limit(1)
            )
        elif mentor_name:
            rows = self._execute_rows(
                self.client.table("mentor_profiles")
                .select("id, user_id, display_name, name, role, about, mentorship_areas, rating, rating_count, profile_picture_url, metadata, yoe, session, money")
                .ilike("display_name", f"%{mentor_name}%")
                .limit(1)
            )
            if not rows:
                rows = self._execute_rows(
                    self.client.table("mentor_profiles")
                    .select("id, user_id, display_name, name, role, about, mentorship_areas, rating, rating_count, profile_picture_url, metadata, yoe, session, money")
                    .ilike("name", f"%{mentor_name}%")
                    .limit(1)
                )
        else:
            return {}

        if not rows:
            return {}
        return self._mentor_to_result(rows[0])

    def get_mentor_availability(self, mentor_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        result_limit = limit or self.settings.default_results_limit
        rows = self._execute_rows(
            self.client.table("mentor_availability_slots")
            .select("id, mentor_id, start_at, end_at, is_active, is_recurring")
            .eq("mentor_id", mentor_id)
            .eq("is_active", True)
            .order("start_at", desc=False)
            .limit(result_limit)
        )
        return rows

    def search_jobs(
        self,
        role: str | None = None,
        location: str | None = None,
        keywords: str | None = None,
        max_rate_per_day: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        result_limit = limit or self.settings.job_results_limit
        rows = self._execute_rows(
            self.client.table("jobs")
            .select("id, director_id, title, company_name, location, rate_per_day, job_type, description, requirements, status, application_deadline, created_at")
            .order("created_at", desc=True)
            .limit(max(result_limit * 4, 20))
        )
        jobs = [self._job_to_result(row) for row in rows]

        filtered = jobs
        if role:
            role_lower = role.lower()
            filtered = [job for job in filtered if role_lower in str(job.get("job_type") or "").lower()]
        if location:
            location_lower = location.lower()
            filtered = [job for job in filtered if location_lower in str(job.get("location") or "").lower()]
        if keywords:
            keywords_lower = keywords.lower()
            filtered = [
                job
                for job in filtered
                if keywords_lower in str(job.get("title") or "").lower()
                or keywords_lower in str(job.get("description") or "").lower()
                or keywords_lower in str(job.get("requirements") or "").lower()
            ]
        if max_rate_per_day is not None and max_rate_per_day > 0:
            filtered = [
                job
                for job in filtered
                if job.get("rate_per_day") is not None and int(job["rate_per_day"]) <= max_rate_per_day
            ]
        return filtered[:result_limit]

    def recommend_mentors_for_user(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        result_limit = limit or self.settings.default_results_limit
        profile = self.get_user_profile(user_id)
        bookings = self.get_user_bookings(user_id, limit=10)

        interest_terms: set[str] = set()
        bio = str(profile.get("bio") or "").strip()
        role = str(profile.get("role") or "").strip()
        if bio:
            interest_terms.update(token.lower() for token in bio.replace(",", " ").split() if len(token) > 4)
        if role:
            interest_terms.add(role.lower())
        for booking in bookings:
            for area in booking.get("mentor_specialties", []):
                interest_terms.add(str(area).lower())

        mentors = self.search_mentors(limit=max(result_limit * 3, 12))
        scored: list[tuple[int, dict[str, Any]]] = []
        for mentor in mentors:
            score = int(round(float(mentor.get("rating") or 0) * 10))
            specialties = [item.lower() for item in mentor.get("specialties", [])]
            if role and role.lower() in str(mentor.get("headline") or "").lower():
                score += 8
            score += sum(6 for item in specialties if item in interest_terms)
            if mentor.get("starting_price_inr") is not None:
                score += 2
            scored.append((score, mentor))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [mentor for _, mentor in scored[:result_limit]]
