import json
import logging
import re

from app.models.schemas import IntentResult, IntentType
from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)

# Keyword patterns for fast classification (checked before calling Claude)
INTENT_KEYWORDS: dict[IntentType, list[str]] = {
    IntentType.BUNDLE: [
        "bundle", "srs", "generate bundle", "implementation bundle", "create bundle",
        "scoping document", "upload srs", "concepts.json", "forms.json",
        "formmappings", "groupprivilege", "zip file", "bundle zip",
    ],
    IntentType.RULE: [
        "rule", "skip logic", "calculated field", "validation rule", "decision rule",
        "visit scheduling rule", "eligibility rule", "javascript rule", "rules.js",
        "write a rule", "create rule", "fix rule", "rule error",
    ],
    IntentType.VOICE: [
        "voice", "transcript", "speech", "spoken", "dictation", "voice capture",
        "voice data", "audio", "voice to form", "speech to text",
    ],
    IntentType.IMAGE: [
        "image", "photo", "picture", "scan", "register photo", "extract from image",
        "ocr", "camera", "photograph", "image extraction",
    ],
    IntentType.CONFIG: [
        "create subject", "create program", "create encounter", "create form",
        "add concept", "configure", "setup avni", "create user",
        "add location", "catchment", "avni api", "crud",
    ],
    IntentType.SUPPORT: [
        "error", "bug", "issue", "not working", "sync fail", "sync error",
        "troubleshoot", "help me fix", "broken", "crash", "problem",
        "data missing", "not showing", "upload fail", "not syncing",
        "sync issue", "sync problem",
    ],
    IntentType.KNOWLEDGE: [
        "what is", "how does", "explain", "tell me about", "documentation",
        "avni concept", "data model", "how to use", "best practice",
        "what are", "difference between",
    ],
}


def _keyword_classify(message: str) -> IntentResult | None:
    """Fast keyword-based intent classification.

    Returns an IntentResult if a strong keyword match is found, otherwise None
    to signal that Claude should handle the classification.
    """
    lower = message.lower().strip()

    scores: dict[IntentType, float] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        match_count = 0
        for kw in keywords:
            if kw in lower:
                match_count += 1
        if match_count > 0:
            # Score based on both absolute match count and proportion.
            # A single keyword match should give a base confidence of ~0.35,
            # two matches ~0.55, three+ matches ~0.70+.
            base = min(match_count * 0.25, 0.70)
            proportion_bonus = (match_count / len(keywords)) * 0.25
            scores[intent] = min(base + proportion_bonus, 0.95)

    if not scores:
        return None

    best_intent = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_intent]

    # Only return a keyword match if we have a reasonable confidence
    if best_score >= 0.1:
        return IntentResult(
            intent=best_intent,
            confidence=best_score,
            extracted_params=_extract_params(lower, best_intent),
        )

    return None


def _extract_params(message: str, intent: IntentType) -> dict:
    """Extract relevant parameters from the message based on detected intent."""
    params: dict = {}

    if intent == IntentType.VOICE:
        # Try to detect language hints
        lang_patterns = {
            "hindi": "hi", "marathi": "mr", "gujarati": "gu",
            "tamil": "ta", "telugu": "te", "kannada": "kn",
            "bengali": "bn", "odia": "or", "english": "en",
        }
        for lang_name, lang_code in lang_patterns.items():
            if lang_name in message:
                params["language"] = lang_code
                break

    elif intent == IntentType.BUNDLE:
        # Check if the user mentions a specific org name
        org_match = re.search(r"(?:for|org|organisation|organization)\s+['\"]?(\w[\w\s]+)", message)
        if org_match:
            params["org_name"] = org_match.group(1).strip()

    return params


CLASSIFY_SYSTEM_PROMPT = """You are an intent classifier for the Avni AI platform. Given a user message, classify it into exactly one intent category.

Categories:
- bundle: User wants to generate an implementation bundle from SRS data or scoping documents
- rule: User wants to create, fix, or understand JavaScript rules (skip logic, calculations, scheduling)
- voice: User wants to map a voice transcript to form fields
- image: User wants to extract data from an image into form fields
- config: User wants to create or modify Avni entities (subjects, programs, encounters, forms, concepts) via API
- support: User is troubleshooting an error or problem with their Avni setup
- knowledge: User is asking a general question about Avni concepts, data model, or best practices
- chat: General conversation that does not fit other categories

Respond with ONLY a JSON object in this exact format:
{"intent": "<category>", "confidence": <0.0-1.0>, "extracted_params": {}}

Do not include any other text."""


async def classify_intent(message: str, attachments: list | None = None) -> IntentResult:
    """Classify a user message into an intent category.

    Uses keyword matching first for speed. Falls back to Claude for ambiguous messages.
    """
    # Check for attachments that strongly signal intent
    if attachments:
        for att in attachments:
            if att.type == "image":
                return IntentResult(
                    intent=IntentType.IMAGE,
                    confidence=0.90,
                    extracted_params={"has_image": True},
                )
            if att.type == "file" and att.filename:
                lower_name = att.filename.lower()
                if lower_name.endswith((".xlsx", ".xls", ".csv")):
                    return IntentResult(
                        intent=IntentType.BUNDLE,
                        confidence=0.90,
                        extracted_params={"filename": att.filename},
                    )
                if lower_name.endswith(".json"):
                    return IntentResult(
                        intent=IntentType.BUNDLE,
                        confidence=0.80,
                        extracted_params={"filename": att.filename},
                    )

    # Try fast keyword classification
    keyword_result = _keyword_classify(message)
    if keyword_result is not None and keyword_result.confidence >= 0.25:
        return keyword_result

    # Fall back to Claude for ambiguous messages
    try:
        response_text = await claude_client.complete(
            messages=[{"role": "user", "content": message}],
            system_prompt=CLASSIFY_SYSTEM_PROMPT,
        )

        # Parse the JSON response
        cleaned = response_text.strip()
        # Handle potential markdown code blocks
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return IntentResult(
            intent=IntentType(data["intent"]),
            confidence=float(data.get("confidence", 0.7)),
            extracted_params=data.get("extracted_params", {}),
        )
    except Exception as e:
        logger.warning("Claude classification failed, defaulting to chat: %s", e)
        return IntentResult(
            intent=IntentType.CHAT,
            confidence=0.5,
            extracted_params={},
        )
