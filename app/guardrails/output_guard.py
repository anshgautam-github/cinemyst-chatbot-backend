from __future__ import annotations

import logging
import re

from .result import GuardrailResult

logger = logging.getLogger(__name__)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║  CONFIGURATION                                                   ║
# ╚═══════════════════════════════════════════════════════════════════╝

# Responses longer than this are likely a context dump or runaway generation.
MAX_RESPONSE_LENGTH = 4000


# ╔═══════════════════════════════════════════════════════════════════╗
# ║  RAW JSON / TOOL OUTPUT LEAK DETECTION                           ║
# ║                                                                  ║
# ║  The system prompt tells the LLM "never return raw JSON," but    ║
# ║  LLMs sometimes ignore this. These patterns catch database       ║
# ║  column names and JSON structures that should never appear in    ║
# ║  natural-language responses.                                      ║
# ╚═══════════════════════════════════════════════════════════════════╝

_JSON_LEAK_INDICATORS = [
    r"^\s*[\[{]",  # response starts with [ or { (raw JSON array/object)
    r"\"mentor_id\"\s*:",
    r"\"user_id\"\s*:",
    r"\"booking_id\"\s*:",
    r"\"job_id\"\s*:",
    r"\"recommended_user_id\"\s*:",
    r"\"conversation_id\"\s*:",
    r"\"created_at\"\s*:\s*\"\d{4}-\d{2}",  # timestamp field: "created_at": "2026-..."
    r"\"metadata\"\s*:\s*\{",  # nested metadata object
    r"\"price_cents\"\s*:",
    r"\"slot_id\"\s*:",
]

JSON_LEAK_PATTERNS: list[re.Pattern[str]] = [
    re.compile(pattern) for pattern in _JSON_LEAK_INDICATORS
]

# If this many JSON-like patterns match, it's almost certainly a raw dump
# rather than a response that happens to mention a field name in context.
JSON_LEAK_THRESHOLD = 3


# ╔═══════════════════════════════════════════════════════════════════╗
# ║  PII DETECTION                                                   ║
# ║                                                                  ║
# ║  The LLM has access to user profiles and booking data through    ║
# ║  tools. It could accidentally include another user's email or    ║
# ║  phone number in a response. These patterns catch common PII     ║
# ║  formats so they can be redacted before the user sees them.      ║
# ╚═══════════════════════════════════════════════════════════════════╝

EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

PHONE_PATTERN = re.compile(
    r"(?<!\d)"  # not preceded by a digit (avoids matching inside IDs)
    r"(?:\+?\d{1,3}[-.\s]?)?"  # optional country code: +91, +1-
    r"\(?\d{3}\)?[-.\s]?"  # area code: (123) or 123
    r"\d{3}[-.\s]?"  # next 3 digits
    r"\d{4}"  # last 4 digits
    r"(?!\d)",  # not followed by a digit
)

# Known safe emails that should NOT trigger PII detection
# (e.g., your company's support email used in responses).
SAFE_EMAIL_DOMAINS = {"cinemyst.com", "cinemyst.in"}


# ── Fallback used when the original response is completely replaced ──
SAFE_FALLBACK = (
    "I apologize, but I wasn't able to generate a proper response. "
    "Could you please rephrase your question? I'm here to help with "
    "CineMyst mentors, jobs, and bookings."
)


class OutputGuardrail:
    """
    Validates the LLM's response BEFORE it reaches the user.

    Catches four categories of LLM failure modes:

        1. Empty response     → LLM returned nothing (model error or tool failure)
        2. Raw JSON leak      → LLM dumped tool output instead of converting to natural language
        3. PII leakage        → LLM included emails/phone numbers from database records
        4. Excessive length   → LLM generated a runaway response (possible context dump)

    Design decisions:
    - PII is redacted (replaced with placeholders) rather than blocking the
      entire response, so the user still gets useful content.
    - JSON leak detection uses a threshold (3+ matching patterns) to avoid
      false positives on responses that legitimately mention a field name.
    - Excessive length is truncated at a word boundary rather than blocked,
      since the content is usually fine — just verbose.
    """

    def validate(self, response: str, user_id: str) -> GuardrailResult:
        """
        Run all output checks in sequence.

        Returns:
            GuardrailResult.safe() if the response is clean.
            GuardrailResult.blocked(...) with a sanitized/replacement message if issues found.
        """
        stripped = response.strip()

        # ── Check 1: Empty response ──────────────────────────────────
        # Why: The LLM occasionally returns nothing, especially after
        # tool errors or when the context window is exhausted.
        if not stripped:
            logger.warning("Output guardrail: empty_response | user=%s", user_id)
            return GuardrailResult.blocked(
                violation_type="empty_response",
                user_message=SAFE_FALLBACK,
            )

        # ── Check 2: Raw JSON / tool output leak ─────────────────────
        # Why: Despite the system prompt saying "never return raw JSON,"
        # LLMs sometimes do it anyway — especially with large tool results
        # or when the model "forgets" the formatting instruction.
        json_result = self._check_json_leak(stripped, user_id)
        if not json_result.is_safe:
            return json_result

        # ── Check 3: PII leakage ─────────────────────────────────────
        # Why: Tools return full profile data including emails and phone
        # numbers. The LLM might naively include these in a response
        # like "Here's mentor Rahul's contact: rahul@gmail.com"
        pii_result = self._check_pii_leakage(stripped, user_id)
        if not pii_result.is_safe:
            return pii_result

        # ── Check 4: Excessive length ────────────────────────────────
        # Why: Runaway generation or context dumps can produce extremely
        # long responses that flood the chat UI and waste bandwidth.
        if len(stripped) > MAX_RESPONSE_LENGTH:
            logger.warning(
                "Output guardrail: response_too_long | user=%s | length=%d",
                user_id,
                len(stripped),
            )
            # Truncate at the last word boundary for a clean cut-off.
            truncated = stripped[:MAX_RESPONSE_LENGTH].rsplit(" ", 1)[0]
            return GuardrailResult.blocked(
                violation_type="response_too_long",
                user_message=truncated + "…",
            )

        return GuardrailResult.safe()

    def _check_json_leak(self, response: str, user_id: str) -> GuardrailResult:
        """
        Detect raw JSON or tool output that the LLM failed to humanize.

        Uses a threshold approach: a single match could be a false positive
        (the LLM might legitimately mention "user_id" in context), but
        3+ matches almost certainly means raw database output leaked through.
        """
        match_count = sum(1 for pattern in JSON_LEAK_PATTERNS if pattern.search(response))

        if match_count >= JSON_LEAK_THRESHOLD:
            logger.warning(
                "Output guardrail: json_leak | user=%s | matches=%d/%d",
                user_id,
                match_count,
                len(JSON_LEAK_PATTERNS),
            )
            return GuardrailResult.blocked(
                violation_type="json_leak",
                user_message=SAFE_FALLBACK,
            )
        return GuardrailResult.safe()

    def _check_pii_leakage(self, response: str, user_id: str) -> GuardrailResult:
        """
        Detect and redact personal information in the LLM's response.

        Strategy: Instead of blocking the entire response (which loses
        useful content), we REDACT the PII and return the sanitized version.
        This way the user still gets their answer, minus the sensitive data.

        Emails from known safe domains (e.g., @cinemyst.com) are allowed
        through, since those are company contact addresses, not personal data.
        """
        # Find emails, excluding known-safe company domains
        all_emails = EMAIL_PATTERN.findall(response)
        unsafe_emails = [
            email
            for email in all_emails
            if not any(email.lower().endswith(f"@{domain}") for domain in SAFE_EMAIL_DOMAINS)
        ]

        phones = PHONE_PATTERN.findall(response)

        if not unsafe_emails and not phones:
            return GuardrailResult.safe()

        logger.warning(
            "Output guardrail: pii_leakage | user=%s | emails=%d | phones=%d",
            user_id,
            len(unsafe_emails),
            len(phones),
        )

        # Redact PII while preserving the rest of the response.
        sanitized = response
        for email in unsafe_emails:
            sanitized = sanitized.replace(email, "[email redacted]")
        for phone in phones:
            sanitized = sanitized.replace(phone, "[phone redacted]")

        return GuardrailResult.blocked(
            violation_type="pii_leakage",
            user_message=sanitized,
        )
