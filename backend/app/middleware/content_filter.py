"""Input content filter: PII detection, prompt injection, length limits, language detection.

Enhanced AI safety guardrails:
- India-specific PII patterns (Aadhaar, PAN, Voter ID, Vehicle Registration, Passport)
- Labeled redaction placeholders ([REDACTED_AADHAAR_1], [REDACTED_PAN_1], etc.)
- On-fail actions: fix (auto-correct/redact), exception (block), rephrase (ask user)
- Text normalization before guardrail checks
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ── PII Detection Patterns (India-specific) ──────────────────

PII_PATTERNS: dict[str, re.Pattern] = {
    # Financial — longest digit pattern first (16 digits) to avoid partial matches
    "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    # India-specific identifiers — 12 digits (must come after 16-digit credit card)
    "aadhaar": re.compile(r"\b[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}\b"),
    "pan_india": re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    "voter_id": re.compile(r"\b[A-Z]{3}[0-9]{7}\b"),
    "vehicle_registration": re.compile(
        r"\b[A-Z]{2}[\s-]?\d{1,2}[\s-]?[A-Z]{1,3}[\s-]?\d{4}\b"
    ),
    "passport_india": re.compile(r"\b[A-Z][0-9]{7}\b"),
    # Contact info — 10 digits (must come after 12-digit aadhaar)
    "phone_india": re.compile(r"\b(\+91[\-\s]?)?[6-9]\d{9}\b"),
    "email": re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]{2,}"),
    # API keys / secrets
    "api_key": re.compile(r"(sk-|ghp_|xox[baprs]-|AIza)[a-zA-Z0-9\-_]{20,}"),
}

# Human-readable labels for PII types (used in redaction placeholders)
PII_LABELS: dict[str, str] = {
    "aadhaar": "AADHAAR",
    "pan_india": "PAN",
    "voter_id": "VOTER_ID",
    "vehicle_registration": "VEHICLE_REG",
    "passport_india": "PASSPORT",
    "phone_india": "PHONE",
    "email": "EMAIL",
    "credit_card": "CREDIT_CARD",
    "api_key": "API_KEY",
}

# ── Prompt Injection Detection ───────────────────────────────────────────────

INJECTION_PATTERNS: list[re.Pattern] = [
    # Direct instruction override
    re.compile(r"(?i)ignore\s+(previous|all|above|prior|system)\s+\w*\s*(instructions?|prompts?|rules?)"),
    re.compile(r"(?i)forget\s+(your|all|previous)\s+\w*\s*instructions?"),
    re.compile(r"(?i)disregard\s+(your|all|previous|the)\s+\w*\s*(instructions?|rules?|guidelines?)"),
    # Role manipulation
    re.compile(r"(?i)you\s+are\s+now\s+"),
    re.compile(r"(?i)pretend\s+(you\s+are|to\s+be)\s+"),
    re.compile(r"(?i)act\s+as\s+if\s+you\s+have\s+no\s+restrictions"),
    re.compile(r"(?i)\bjailbreak\b"),
    re.compile(r"(?i)\bDAN\s+mode\b"),
    # System prompt extraction
    re.compile(r"(?i)what\s+is\s+your\s+system\s+prompt"),
    re.compile(r"(?i)reveal\s+(your|the)\s+(system|internal)\s+(prompt|instructions?)"),
    re.compile(r"(?i)output\s+(your|the)\s+(initial|system|original)\s+(prompt|instructions?)"),
    re.compile(r"(?i)repeat\s+(your|the)\s+(system|initial)\s+(prompt|instructions?)\s+(back|verbatim|exactly)"),
    re.compile(r"(?i)show\s+me\s+(your|the)\s+(system|hidden)\s+(prompt|instructions?)"),
    # Encoding-based evasion
    re.compile(r"(?i)base64\s+(decode|encode)\s+(the\s+)?(following|this)"),
    re.compile(r"(?i)translate\s+(the\s+)?following\s+from\s+(base64|hex|rot13)"),
    # Delimiter injection
    re.compile(r"```system"),
    re.compile(r"\[SYSTEM\]"),
    re.compile(r"<\|im_start\|>system"),
    re.compile(r"<\|system\|>"),
]

# ── Language Detection (simple heuristic) ────────────────────────────────────

# Characters from supported scripts (Latin/English + major Indian scripts)
_SUPPORTED_SCRIPT_RE = re.compile(
    r"[\u0000-\u007F"       # Basic Latin (ASCII / English)
    r"\u0900-\u097F"        # Devanagari (Hindi, Marathi, Sanskrit)
    r"\u0980-\u09FF"        # Bengali
    r"\u0A00-\u0A7F"        # Gurmukhi (Punjabi)
    r"\u0A80-\u0AFF"        # Gujarati
    r"\u0B00-\u0B7F"        # Oriya
    r"\u0B80-\u0BFF"        # Tamil
    r"\u0C00-\u0C7F"        # Telugu
    r"\u0C80-\u0CFF"        # Kannada
    r"\u0D00-\u0D7F"        # Malayalam
    r"]"
)

# Maximum content length
MAX_CONTENT_LENGTH = 10_000


# ── On-Fail Action Types ────────────────────────────────────

class OnFailAction:
    """On-fail actions for guardrail triggers."""
    FIX = "fix"             # Auto-correct/redact and continue
    EXCEPTION = "exception"  # Hard block — reject the request
    REPHRASE = "rephrase"   # Ask user to rephrase their message


@dataclass
class ContentFilterResult:
    """Result of running content through the input filter.

    Enhanced fields:
    - action: the on-fail action taken (fix, exception, rephrase)
    - safe_text: sanitized text with PII redacted (labeled placeholders)
    - pii_counts: per-type count of PII detected
    - rephrase_message: if action=rephrase, the prompt to show the user
    """

    passed: bool = True
    pii_detected: list[str] = field(default_factory=list)
    pii_counts: dict[str, int] = field(default_factory=dict)
    injection_detected: bool = False
    injection_patterns: list[str] = field(default_factory=list)
    length_exceeded: bool = False
    unsupported_language: bool = False
    warnings: list[str] = field(default_factory=list)
    block_reason: str | None = None
    # On-fail action fields
    action: str = ""  # fix, exception, rephrase, or empty if passed cleanly
    safe_text: str = ""  # PII-redacted version of the text
    rephrase_message: str = ""  # Message to show user if action=rephrase

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "pii_detected": self.pii_detected,
            "pii_counts": self.pii_counts,
            "injection_detected": self.injection_detected,
            "injection_patterns": self.injection_patterns,
            "length_exceeded": self.length_exceeded,
            "unsupported_language": self.unsupported_language,
            "warnings": self.warnings,
            "block_reason": self.block_reason,
            "action": self.action,
            "rephrase_message": self.rephrase_message,
        }


def _redact_pii(text: str) -> tuple[str, list[str], dict[str, int]]:
    """Replace PII in text with labeled redaction placeholders.

    Example: "My Aadhaar is 1234 5678 9012" -> "My Aadhaar is [REDACTED_AADHAAR_1]"

    Returns:
        (redacted_text, pii_types_found, pii_counts)
    """
    redacted = text
    pii_types_found: list[str] = []
    pii_counts: dict[str, int] = {}

    for pii_type, pattern in PII_PATTERNS.items():
        matches = list(pattern.finditer(redacted))
        if matches:
            label = PII_LABELS.get(pii_type, pii_type.upper())
            if pii_type not in pii_types_found:
                pii_types_found.append(pii_type)
            pii_counts[pii_type] = len(matches)

            # Replace each match with a numbered placeholder
            # Process in reverse to preserve match positions
            counter = len(matches)
            for match in reversed(matches):
                placeholder = f"[REDACTED_{label}_{counter}]"
                redacted = redacted[:match.start()] + placeholder + redacted[match.end():]
                counter -= 1

    return redacted, pii_types_found, pii_counts


def filter_input(text: str) -> ContentFilterResult:
    """Run all input guardrails on the given text.

    Returns a ContentFilterResult with details of any triggers.
    On-fail actions:
    - PII detected -> action="fix", text is redacted with labeled placeholders
    - Injection detected -> action="exception", request is blocked
    - Length exceeded -> action="exception", request is blocked
    """
    result = ContentFilterResult(safe_text=text)

    if not settings.GUARDRAILS_ENABLED:
        return result

    # 0. Normalize text for consistent matching
    from app.services.text_normalizer import normalize_text
    normalized = normalize_text(text)

    # 1. Content length check
    if len(text) > MAX_CONTENT_LENGTH:
        result.passed = False
        result.length_exceeded = True
        result.action = OnFailAction.EXCEPTION
        result.block_reason = f"Message exceeds maximum length of {MAX_CONTENT_LENGTH} characters ({len(text)} provided)"
        return result

    # 2. Prompt injection detection (uses normalized text for better matching)
    if settings.INJECTION_DETECTION_ENABLED:
        for pattern in INJECTION_PATTERNS:
            match = pattern.search(normalized)
            if match:
                result.injection_detected = True
                result.injection_patterns.append(match.group(0)[:50])
        if result.injection_detected:
            result.passed = False
            result.action = OnFailAction.EXCEPTION
            result.block_reason = "Message contains patterns associated with prompt injection"
            logger.warning(
                "Prompt injection detected: %s",
                result.injection_patterns,
            )
            return result

    # 3. PII detection with labeled redaction (fix action — don't block)
    if settings.PII_DETECTION_ENABLED:
        redacted_text, pii_types, pii_counts = _redact_pii(text)
        if pii_types:
            result.pii_detected = pii_types
            result.pii_counts = pii_counts
            result.safe_text = redacted_text
            result.action = OnFailAction.FIX
            result.warnings.append(
                f"PII detected and redacted ({', '.join(pii_types)}). "
                f"Counts: {pii_counts}. "
                "The redacted version will be sent to the AI."
            )
            logger.info("PII detected and redacted: %s (counts: %s)", pii_types, pii_counts)
    else:
        result.safe_text = text

    # 4. Language detection
    if text.strip():
        alpha_chars = [c for c in text if c.isalpha()]
        if alpha_chars:
            supported_count = sum(1 for c in alpha_chars if _SUPPORTED_SCRIPT_RE.match(c))
            ratio = supported_count / len(alpha_chars)
            if ratio < 0.5:
                result.unsupported_language = True
                result.warnings.append(
                    "Your message appears to contain text in an unsupported language. "
                    "Avni AI works best with English and major Indian languages."
                )

    return result


def mask_pii(text: str) -> str:
    """Mask PII in text for logging purposes. Does NOT modify user-facing content.

    Uses labeled redaction placeholders.
    """
    masked, _, _ = _redact_pii(text)
    return masked


def set_rephrase_action(result: ContentFilterResult, message: str) -> ContentFilterResult:
    """Set the rephrase action on a filter result (for ban list triggers).

    Called externally by the chat flow when ban list words are found.
    """
    result.action = OnFailAction.REPHRASE
    result.rephrase_message = message
    result.passed = False
    result.block_reason = message
    return result
