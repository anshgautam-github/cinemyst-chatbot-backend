from __future__ import annotations

import json
from typing import Any

from langchain_groq import ChatGroq

from app.config import Settings


class LLMService:
    """Thin wrapper around Groq-powered tasks used by recommendations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._chat_client = ChatGroq(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0,
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
