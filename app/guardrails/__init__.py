"""
Guardrails module — input and output validation for the chatbot.

Input guardrails run BEFORE the LLM to block unsafe messages (zero cost).
Output guardrails run AFTER the LLM to catch unsafe responses (sanitize before user sees them).
"""

from .input_guard import InputGuardrail
from .output_guard import OutputGuardrail
from .result import GuardrailResult

__all__ = ["GuardrailResult", "InputGuardrail", "OutputGuardrail"]
