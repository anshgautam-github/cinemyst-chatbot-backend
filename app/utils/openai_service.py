from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import Settings


class OpenAIService:
    """Thin wrapper around OpenAI-powered tasks used by recommendations."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embedding_client = OpenAIEmbeddings(
            api_key=settings.openai_api_key,
            model="text-embedding-3-small",
        )
        self._chat_client = ChatOpenAI(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            temperature=0,
        )

    async def generate_embedding(self, text: str) -> list[float]:
        """Create a semantic vector for a profile summary that can be compared later."""
        cleaned_text = text.strip()
        if not cleaned_text:
            return []
        embedding = await self._embedding_client.aembed_query(cleaned_text)
        return [float(value) for value in embedding]

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
            raise ValueError("OpenAI interest extraction did not return valid JSON.") from error

        if not isinstance(parsed, list):
            raise ValueError("OpenAI interest extraction must return a JSON array.")

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
