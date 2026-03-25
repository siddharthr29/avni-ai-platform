"""Output guardrails: response sanitization, hallucination markers, code injection prevention, bundle safety.

Enhanced AI safety guardrails:
- Gender bias detection and neutral term substitution (output stage)
- PII re-check on output (catch LLM-generated PII)
- Ban list check on output (catch LLM responses containing banned terms)

Applied to every LLM response before it reaches the user.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ── System Prompt Fragment Detection ─────────────────────────────────────────

# Fragments from AVNI_SYSTEM_PROMPT that should never appear in output
_SYSTEM_PROMPT_FRAGMENTS = [
    "You are the Avni Platform Architect",
    "foremost expert on the Avni field data collection platform",
    "AVNI DATA MODEL",
    "BUNDLE FILE ORDER (CRITICAL)",
    "HOW YOU RESPOND",
    "MANDATORY: Before writing any rule",
    "Internal Reference Knowledge (from Avni's training corpus)",
    "NEVER tell the user they provided this data",
    "NEVER say 'the concepts you provided'",
    "This is background knowledge, not user input",
    "--- User's Organisation ---",
    "--- ACTION: Bundle Creation ---",
    "--- ACTION: Organisation Setup ---",
    "IMPORTANT RULES:",
    "RESPONSIBLE AI GUIDELINES",
]

# Compile for fast matching
_SYSTEM_FRAGMENT_PATTERNS = [
    re.compile(re.escape(frag), re.IGNORECASE)
    for frag in _SYSTEM_PROMPT_FRAGMENTS
]

# ── Code Injection Patterns ──────────────────────────────────────────────────

_SCRIPT_INJECTION_PATTERNS = [
    re.compile(r"<script\b[^>]*>.*?</script>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<iframe\b[^>]*>.*?</iframe>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<object\b[^>]*>.*?</object>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<embed\b[^>]*>", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"on\w+\s*=\s*[\"'][^\"']*[\"']", re.IGNORECASE),  # onclick="..." etc
    re.compile(r"data:text/html", re.IGNORECASE),
]

# Patterns to detect in markdown code blocks (these are OK in code blocks, bad outside)
_OUTSIDE_CODEBLOCK_SCRIPT_RE = re.compile(r"<script\b", re.IGNORECASE)

# ── Bundle Safety Patterns ───────────────────────────────────────────────────

_SQL_INJECTION_PATTERNS = [
    re.compile(r";\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|EXEC)\s", re.IGNORECASE),
    re.compile(r"'\s*(OR|AND)\s+\d+\s*=\s*\d+", re.IGNORECASE),
    re.compile(r"UNION\s+(ALL\s+)?SELECT", re.IGNORECASE),
    re.compile(r"--\s*$", re.MULTILINE),  # SQL comment at end of line
]

_BUNDLE_NAME_INJECTION_PATTERNS = [
    re.compile(r"<script\b", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"[\"']\s*;\s*(DROP|DELETE|ALTER)", re.IGNORECASE),
    re.compile(r"\$\{.*\}"),  # Template injection
    re.compile(r"\{\{.*\}\}"),  # Template injection (Jinja/Handlebars)
]

# ── Low Confidence Marker ────────────────────────────────────────────────────

LOW_CONFIDENCE_NOTE = (
    "[Note: This response may not be fully accurate for your specific Avni setup. "
    "Please verify against your organisation's configuration.]"
)


@dataclass
class OutputGuardResult:
    """Result of running output through guardrails."""

    original_text: str = ""
    sanitized_text: str = ""
    system_prompt_leaked: bool = False
    script_injection_found: bool = False
    low_confidence_warning: bool = False
    gender_bias_fixed: bool = False
    gender_bias_substitutions: list[dict] = field(default_factory=list)
    ban_list_triggered: bool = False
    banned_words_found: list[dict] = field(default_factory=list)
    pii_redacted_in_output: bool = False
    modifications: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system_prompt_leaked": self.system_prompt_leaked,
            "script_injection_found": self.script_injection_found,
            "low_confidence_warning": self.low_confidence_warning,
            "gender_bias_fixed": self.gender_bias_fixed,
            "gender_bias_substitutions": self.gender_bias_substitutions,
            "ban_list_triggered": self.ban_list_triggered,
            "banned_words_found": self.banned_words_found,
            "pii_redacted_in_output": self.pii_redacted_in_output,
            "modifications": self.modifications,
        }


def guard_output(
    text: str,
    rag_confidence: float | None = None,
    org_id: str = "",
) -> OutputGuardResult:
    """Run all output guardrails on LLM response text.

    Enhanced safety checks:
    1. System prompt leak detection
    2. Script injection sanitization
    3. Gender bias detection and neutral substitution
    4. PII detection in output (catch LLM-generated PII)
    5. Ban list check on output (org-scoped)
    6. Low confidence warning

    Args:
        text: The raw LLM response text.
        rag_confidence: Average RAG retrieval confidence (0-1). If below threshold,
                        a low-confidence warning is prepended.
        org_id: Organisation ID for ban list scoping.

    Returns:
        OutputGuardResult with sanitized text and metadata about any triggers.
    """
    result = OutputGuardResult(original_text=text, sanitized_text=text)

    if not settings.GUARDRAILS_ENABLED:
        return result

    sanitized = text

    # 1. Strip leaked system prompt fragments
    for pattern in _SYSTEM_FRAGMENT_PATTERNS:
        if pattern.search(sanitized):
            result.system_prompt_leaked = True
            # Remove the line containing the fragment
            lines = sanitized.split("\n")
            cleaned_lines = []
            for line in lines:
                if not pattern.search(line):
                    cleaned_lines.append(line)
                else:
                    result.modifications.append(
                        f"Removed line containing system prompt fragment"
                    )
            sanitized = "\n".join(cleaned_lines)

    if result.system_prompt_leaked:
        logger.warning("System prompt fragment detected and removed from LLM output")

    # 2. Sanitize script injection outside code blocks
    sanitized = _sanitize_scripts_outside_codeblocks(sanitized, result)

    # 3. Gender bias check (output stage fix action)
    try:
        from app.services.gender_bias_guard import check_gender_bias
        bias_result = check_gender_bias(sanitized)
        if bias_result["has_bias"]:
            result.gender_bias_fixed = True
            result.gender_bias_substitutions = bias_result["substitutions"]
            sanitized = bias_result["fixed_text"]
            sub_summary = ", ".join(
                f'"{s["original"]}"->"{s["neutral"]}"' for s in bias_result["substitutions"]
            )
            result.modifications.append(
                f"Gender bias: substituted neutral terms ({sub_summary})"
            )
    except Exception as e:
        logger.debug("Gender bias check skipped: %s", e)

    # 4. PII detection in output (catch LLM-generated PII and redact)
    try:
        from app.middleware.content_filter import _redact_pii
        redacted_output, pii_types, pii_counts = _redact_pii(sanitized)
        if pii_types:
            result.pii_redacted_in_output = True
            sanitized = redacted_output
            result.modifications.append(
                f"PII redacted in output ({', '.join(pii_types)})"
            )
    except Exception as e:
        logger.debug("Output PII check skipped: %s", e)

    # 5. Ban list check on output (org-scoped, fix action)
    if org_id:
        try:
            import asyncio
            from app.services.ban_list import check_ban_list
            # Run async check synchronously since guard_output is sync
            # This works because we're called from an async context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # We're in an async context — schedule a coroutine
                # Use the sync _get_effective_ban_list + manual check instead
                from app.services.ban_list import _get_effective_ban_list, _build_word_pattern
                ban_entries = _get_effective_ban_list(org_id)
                for entry in ban_entries:
                    pattern = _build_word_pattern(entry["word"])
                    if pattern.search(sanitized):
                        result.ban_list_triggered = True
                        result.banned_words_found.append(entry)
                        sanitized = pattern.sub("[BANNED]", sanitized)
                if result.ban_list_triggered:
                    banned_words = [b["word"] for b in result.banned_words_found]
                    result.modifications.append(
                        f"Ban list: removed banned terms ({', '.join(banned_words)})"
                    )
        except Exception as e:
            logger.debug("Output ban list check skipped: %s", e)

    # 6. Low confidence warning
    if rag_confidence is not None and rag_confidence < settings.LOW_CONFIDENCE_THRESHOLD:
        result.low_confidence_warning = True
        result.modifications.append("Added low-confidence warning")
        sanitized = f"{LOW_CONFIDENCE_NOTE}\n\n{sanitized}"

    result.sanitized_text = sanitized
    return result


def _sanitize_scripts_outside_codeblocks(text: str, result: OutputGuardResult) -> str:
    """Remove script/iframe tags that appear outside markdown code blocks."""
    # Split text into code blocks and non-code blocks
    parts = re.split(r"(```[\s\S]*?```|`[^`]+`)", text)
    sanitized_parts = []

    for i, part in enumerate(parts):
        # Odd indices are code blocks (from the split), leave them alone
        if i % 2 == 1:
            sanitized_parts.append(part)
        else:
            modified = part
            for pattern in _SCRIPT_INJECTION_PATTERNS:
                if pattern.search(modified):
                    result.script_injection_found = True
                    modified = pattern.sub("[REMOVED_UNSAFE_CONTENT]", modified)
                    result.modifications.append("Removed unsafe HTML/script content from response")
            sanitized_parts.append(modified)

    return "".join(sanitized_parts)


def validate_bundle_names(bundle_data: dict) -> list[str]:
    """Validate that bundle concept names, form names, etc. don't contain injection patterns.

    Args:
        bundle_data: The bundle JSON data (concepts, forms, etc.)

    Returns:
        List of warning messages for any unsafe names found.
    """
    warnings: list[str] = []

    if not settings.GUARDRAILS_ENABLED:
        return warnings

    def _check_name(name: str, context: str) -> None:
        if not isinstance(name, str):
            return
        for pattern in _BUNDLE_NAME_INJECTION_PATTERNS:
            if pattern.search(name):
                warnings.append(
                    f"Potentially unsafe content in {context}: '{name[:50]}'"
                )
                break
        for pattern in _SQL_INJECTION_PATTERNS:
            if pattern.search(name):
                warnings.append(
                    f"SQL injection pattern detected in {context}: '{name[:50]}'"
                )
                break

    # Check concepts
    if isinstance(bundle_data, dict):
        for concept in bundle_data.get("concepts", []):
            if isinstance(concept, dict):
                _check_name(concept.get("name", ""), "concept name")

        # Check forms
        for form in bundle_data.get("forms", []):
            if isinstance(form, dict):
                _check_name(form.get("name", ""), "form name")
                for group in form.get("formElementGroups", []):
                    if isinstance(group, dict):
                        _check_name(group.get("name", ""), "form element group name")
                        for elem in group.get("formElements", []):
                            if isinstance(elem, dict):
                                _check_name(elem.get("name", ""), "form element name")

        # Check subject types
        for st in bundle_data.get("subjectTypes", []):
            if isinstance(st, dict):
                _check_name(st.get("name", ""), "subject type name")

        # Check programs
        for prog in bundle_data.get("programs", []):
            if isinstance(prog, dict):
                _check_name(prog.get("name", ""), "program name")

        # Check encounter types
        for et in bundle_data.get("encounterTypes", []):
            if isinstance(et, dict):
                _check_name(et.get("name", ""), "encounter type name")

    return warnings
