from __future__ import annotations

import json
from typing import Any

from langchain_groq import ChatGroq

from app.config import Settings
from app.schemas import CastingDraftResponse


class LLMService:
    """Thin wrapper around Groq-powered tasks used by recommendations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._chat_client = ChatGroq(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0,
        )
        self._casting_client = ChatGroq(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.4,
        )

    async def extract_interests(self, bio: str, interest_list: list[str]) -> list[str]:
        """Ask the model to map free-form profile text onto the fixed interest taxonomy."""
        if not bio.strip() or not interest_list:
            return []

        prompt = (
            "Given this user bio, return ONLY matching categories from this list:\n"
            f"{json.dumps(interest_list, ensure_ascii=False)}\n"
            "Return a JSON array. Do not add extra text.\n\n"
            f"Bio:\n{bio.strip()}"
        )

        response = await self._chat_client.ainvoke(prompt)
        content = self._coerce_text(response.content)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise ValueError("Groq interest extraction did not return valid JSON.") from error

        if not isinstance(parsed, list):
            raise ValueError("Groq interest extraction must return a JSON array.")

        results: list[str] = []
        for item in parsed:
            if isinstance(item, str):
                cleaned_item = item.strip()
                if cleaned_item:
                    results.append(cleaned_item)
        return results

    async def generate_casting_draft(self, rough_idea: str, context: str) -> CastingDraftResponse:
        """Generate a structured casting-post draft for the job-posting flow."""
        prompt = self._build_casting_draft_prompt(rough_idea=rough_idea, context=context)
        response = await self._casting_client.ainvoke(prompt)
        content = self._coerce_text(response.content)
        payload = self._extract_json_object(content)

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as error:
            raise ValueError("Casting AI did not return valid JSON.") from error

        if not isinstance(parsed, dict):
            raise ValueError("Casting AI must return a JSON object.")

        normalized = {
            "project_title": self._clean_text(parsed.get("project_title")),
            "project_type": self._normalize_choice(
                parsed.get("project_type"),
                ["Web Series", "TV", "Film", "Short Film", "Ad/Commercial"],
            ),
            "character_name": self._clean_text(parsed.get("character_name")),
            "character_description": self._clean_text(parsed.get("character_description")),
            "age_range": self._clean_text(parsed.get("age_range")),
            "gender": self._normalize_choice(
                parsed.get("gender"),
                ["Male", "Female", "Non-Binary", "Any"],
            ),
            "position": self._normalize_choice(
                parsed.get("position"),
                ["Lead Actor", "Supporting", "Junior Artist", "Child Artist"],
            ),
            "genre": self._normalize_choice(
                parsed.get("genre"),
                ["Drama", "Comedy", "Action", "Horror", "Sci-Fi", "Romance", "Thriller"],
            ),
        }
        return CastingDraftResponse(**normalized)

    def _build_casting_draft_prompt(self, rough_idea: str, context: str) -> str:
        return f"""
You are CineMyst's AI Casting Post Generator for film directors and casting professionals.
Create a polished, concise casting role draft from the rough idea and any fields already entered.
Use the input as inspiration only. Generate fresh, professional copy for every field.
Do not copy the rough idea or existing context verbatim into the output.
If a title or description is already present, improve it instead of repeating it exactly.

Return ONLY valid JSON. Do not include markdown, backticks, comments, or extra prose.

JSON schema:
{{
  "project_title": "Professional project title, keep existing title if provided",
  "project_type": "One of: Web Series, TV, Film, Short Film, Ad/Commercial",
  "character_name": "Character name",
  "character_description": "Professional casting description in 3-5 sentences. Include performance tone, personality, actor expectations, and screen presence requirements.",
  "age_range": "Example: 20-30",
  "gender": "One of: Male, Female, Non-Binary, Any",
  "position": "One of: Lead Actor, Supporting, Junior Artist, Child Artist",
  "genre": "One of: Drama, Comedy, Action, Horror, Sci-Fi, Romance, Thriller"
}}

Keep the result realistic for an Indian film/casting app. Avoid fake guarantees, discrimination, unsafe claims, or overly long text.
The existing form context is a hint, not a template. Do not preserve draft wording exactly.

Rough role idea:
{rough_idea.strip() or "Not provided"}

Existing form context:
{context.strip() or "Not provided"}
""".strip()

    def _extract_json_object(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise ValueError("Casting AI response was not valid JSON.")
        return stripped[start : end + 1]

    def _clean_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None

    def _normalize_choice(self, value: Any, options: list[str]) -> str | None:
        cleaned = self._clean_text(value)
        if not cleaned:
            return None

        for option in options:
            if option.casefold() == cleaned.casefold():
                return option
        return cleaned

    def _coerce_text(self, content: Any) -> str:
        """Flatten LangChain response content into plain text before JSON parsing."""
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts).strip()

        return str(content).strip()
