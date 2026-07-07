from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """
    Outcome of a single guardrail check.

    Every guardrail method returns this object. Consumers only need to
    check `is_safe` — if it's False, `user_message` contains a safe,
    non-revealing message to show the end user, and `violation_type`
    identifies the category for logging and metrics.
    """

    is_safe: bool
    violation_type: str | None = None
    user_message: str | None = None

    # ── Factory helpers ──────────────────────────────────────────────
    # These keep the calling code clean and self-documenting.

    @classmethod
    def safe(cls) -> GuardrailResult:
        """All checks passed — the content is safe to proceed."""
        return cls(is_safe=True)

    @classmethod
    def blocked(cls, violation_type: str, user_message: str) -> GuardrailResult:
        """A check failed — include the category and a user-safe message."""
        return cls(is_safe=False, violation_type=violation_type, user_message=user_message)
