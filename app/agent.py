from __future__ import annotations

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessageChunk
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

from .config import Settings
from .guardrails import InputGuardrail, OutputGuardrail
from .prompts import build_system_prompt
from .supabase_service import SupabaseService
from .tools import build_tools


class CineMystChatAgent:
    """Owns the AI chat workflow from prompt creation through stored conversation history."""

    def __init__(
        self, 
        settings: Settings, 
        supabase_service: SupabaseService,
        input_guard: InputGuardrail,
        output_guard: OutputGuardrail,
    ) -> None:
        self.settings = settings
        self.supabase_service = supabase_service
        self.input_guard = input_guard
        self.output_guard = output_guard
        self.tools = build_tools(supabase_service)

    def _build_user_summary(self, user_id: str) -> str:
        """Build the compact user context that gets injected into the system prompt."""
        profile = self.supabase_service.get_user_profile(user_id)
        bookings = self.supabase_service.get_user_bookings(user_id, limit=3)

        full_name = profile.get("full_name") or profile.get("username") or "Unknown user"
        role = profile.get("role") or "unknown role"
        city = profile.get("location_city") or ""
        state = profile.get("location_state") or ""
        bio = profile.get("bio") or ""
        location = ", ".join([part for part in [city, state] if part])

        recent_booking_summary = ", ".join(
            booking.get("mentor_name", "Unknown mentor") for booking in bookings[:3]
        ) or "no recent bookings"

        return (
            f"Name: {full_name}. "
            f"Role: {role}. "
            f"Location: {location or 'unknown'}. "
            f"Bio: {bio or 'none'}. "
            f"Recent bookings: {recent_booking_summary}."
        )

    def _build_agent(self, user_id: str):
        """Create a fresh LangGraph agent per request using the current user context."""
        model = ChatGroq(
            api_key=self.settings.groq_api_key,
            model_name=self.settings.groq_model,
            temperature=0.2,
        )
        prompt = build_system_prompt(user_id=user_id, user_summary=self._build_user_summary(user_id))
        return create_react_agent(
            model=model,
            tools=self.tools,
            prompt=prompt,
        )

    def _build_message_history(self, user_id: str, conversation_id: str) -> list[dict[str, str]]:
        """Load stored messages and reshape them into the format expected by LangGraph."""
        history = self.supabase_service.get_conversation_messages(
            user_id=user_id,
            conversation_id=conversation_id,
            limit=40,
        )
        return [
            {"role": str(item.get("role") or "user"), "content": str(item.get("content") or "")}
            for item in history
            if item.get("content")
        ]

    def chat(self, user_id: str, message: str, conversation_id: str) -> tuple[str, str]:
        """Run a full request/response chat cycle and persist both user and assistant messages."""
        # ── INPUT GUARDRAIL ─────────────────────────────────────────
        input_result = self.input_guard.validate(message, user_id)
        if not input_result.is_safe:
            return input_result.user_message or "Request blocked.", self._build_user_summary(user_id)

        self.supabase_service.ensure_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            seed_message=message,
        )
        agent = self._build_agent(user_id)
        prior_messages = self._build_message_history(user_id=user_id, conversation_id=conversation_id)
        result = agent.invoke(
            # We pass earlier messages explicitly so the chat can resume across app sessions.
            {"messages": [*prior_messages, {"role": "user", "content": message}]},
        )
        messages = result.get("messages", [])
        if not messages:
            return "I couldn't generate a response right now.", self._build_user_summary(user_id)

        final_message = messages[-1]
        content = getattr(final_message, "content", "")
        if isinstance(content, list):
            content = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        answer = str(content).strip() or "I couldn't generate a response right now."

        # ── OUTPUT GUARDRAIL ────────────────────────────────────────
        output_result = self.output_guard.validate(answer, user_id)
        final_answer = answer if output_result.is_safe else (output_result.user_message or answer)

        self.supabase_service.save_conversation_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=message,
        )
        self.supabase_service.save_conversation_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=final_answer,
        )
        return final_answer, self._build_user_summary(user_id)

    async def stream_chat(
        self, user_id: str, message: str, conversation_id: str
    ) -> AsyncIterator[str]:
        """Stream a response token-by-token while still persisting the final answer at the end."""
        # ── INPUT GUARDRAIL ─────────────────────────────────────────
        input_result = self.input_guard.validate(message, user_id)
        if not input_result.is_safe:
            yield input_result.user_message or "Request blocked."
            return

        self.supabase_service.ensure_conversation(
            user_id=user_id,
            conversation_id=conversation_id,
            seed_message=message,
        )
        agent = self._build_agent(user_id)
        prior_messages = self._build_message_history(user_id=user_id, conversation_id=conversation_id)
        streamed_any = False
        collected_parts: list[str] = []

        async for chunk in agent.astream(
            {"messages": [*prior_messages, {"role": "user", "content": message}]},
            stream_mode="messages",
        ):
            token_text = self._extract_stream_text(chunk)
            if token_text:
                streamed_any = True
                collected_parts.append(token_text)
                yield token_text

        if not streamed_any:
            fallback_answer, _ = self.chat(
                user_id=user_id,
                message=message,
                conversation_id=conversation_id,
            )
            if fallback_answer:
                yield fallback_answer
            return

        answer = "".join(collected_parts).strip()
        
        # ── OUTPUT GUARDRAIL ────────────────────────────────────────
        # For streaming, the user already saw the tokens as they were generated.
        # But we still run the output guard before saving to the database to ensure
        # that PII or JSON dumps aren't permanently persisted into the chat history.
        output_result = self.output_guard.validate(answer, user_id)
        final_answer = answer if output_result.is_safe else (output_result.user_message or answer)

        self.supabase_service.save_conversation_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="user",
            content=message,
        )
        self.supabase_service.save_conversation_message(
            conversation_id=conversation_id,
            user_id=user_id,
            role="assistant",
            content=final_answer or "I couldn't generate a response right now.",
        )

    def _extract_stream_text(self, chunk: object) -> str:
        """Normalize the different chunk shapes returned during streaming into plain text."""
        if isinstance(chunk, tuple):
            if chunk:
                text = self._extract_stream_text(chunk[0])
                if text:
                    return text
            return ""

        if not isinstance(chunk, AIMessageChunk):
            return ""

        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)

        return ""
