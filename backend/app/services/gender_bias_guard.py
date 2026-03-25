"""Gender assumption bias validator for AI-generated content.

Detects gendered language in AI outputs and suggests neutral alternatives.
Applied primarily on OUTPUT stage (not input, to avoid intent drift).
Categories: generic, healthcare, education.
"""

import logging
import re

from app.config import settings

logger = logging.getLogger(__name__)


# ── Gender-Neutral Replacement Maps ──────────────────────────────────────────
# Gender-neutral language mappings for Indian NGO health/education contexts.

GENDER_NEUTRAL_MAP: dict[str, dict[str, str]] = {
    "generic": {
        "chairman": "chairperson",
        "chairmen": "chairpersons",
        "policeman": "police officer",
        "policemen": "police officers",
        "policewoman": "police officer",
        "fireman": "firefighter",
        "firemen": "firefighters",
        "mankind": "humanity",
        "manpower": "workforce",
        "manmade": "artificial",
        "man-made": "artificial",
        "housewife": "homemaker",
        "housewives": "homemakers",
        "businessman": "businessperson",
        "businessmen": "businesspeople",
        "businesswoman": "businessperson",
        "salesman": "salesperson",
        "salesmen": "salespeople",
        "foreman": "supervisor",
        "mailman": "mail carrier",
        "stewardess": "flight attendant",
        "steward": "flight attendant",
        "actress": "actor",
        "waitress": "server",
        "waiter": "server",
        "spokesman": "spokesperson",
        "spokeswoman": "spokesperson",
        "craftsman": "artisan",
        "craftsmen": "artisans",
        "layman": "layperson",
        "laymen": "laypeople",
        "he/she": "they",
        "his/her": "their",
        "him/her": "them",
        "s/he": "they",
    },
    "healthcare": {
        "lady doctor": "doctor",
        "female doctor": "doctor",
        "male nurse": "nurse",
        "midwife": "birth attendant",
        "maternity leave": "parental leave",
        "cleaning lady": "cleaner",
        "cleaning woman": "cleaner",
    },
    "education": {
        "headmistress": "head teacher",
        "headmaster": "head teacher",
        "schoolmaster": "teacher",
        "schoolmistress": "teacher",
        "schoolmasters": "teachers",
    },
}


def _build_pattern_map(categories: list[str]) -> dict[re.Pattern, tuple[str, str, str]]:
    """Build compiled regex patterns for the requested categories.

    Returns dict of pattern -> (original_word, neutral_word, category).
    Multi-word terms are matched first (longer patterns take priority).
    """
    entries: list[tuple[str, str, str]] = []  # (gendered, neutral, category)
    for cat in categories:
        cat_map = GENDER_NEUTRAL_MAP.get(cat, {})
        for gendered, neutral in cat_map.items():
            entries.append((gendered, neutral, cat))

    # Sort by length descending so multi-word terms match before single-word substrings
    entries.sort(key=lambda e: len(e[0]), reverse=True)

    pattern_map: dict[re.Pattern, tuple[str, str, str]] = {}
    for gendered, neutral, cat in entries:
        # Word boundary matching, case-insensitive
        pattern = re.compile(r"\b" + re.escape(gendered) + r"\b", re.IGNORECASE)
        pattern_map[pattern] = (gendered, neutral, cat)
    return pattern_map


def check_gender_bias(
    text: str,
    categories: list[str] | None = None,
) -> dict:
    """Check text for gendered language and provide neutral alternatives.

    Args:
        text: The text to check (typically LLM output).
        categories: Which category maps to check. Default: all three.

    Returns:
        {
            "has_bias": bool,
            "substitutions": [{"original": str, "neutral": str, "category": str, "count": int}],
            "fixed_text": str,
        }
    """
    if not settings.GENDER_BIAS_CHECK_ENABLED:
        return {"has_bias": False, "substitutions": [], "fixed_text": text}

    if categories is None:
        categories = ["generic", "healthcare", "education"]

    pattern_map = _build_pattern_map(categories)

    substitutions: list[dict] = []
    fixed_text = text

    for pattern, (original, neutral, category) in pattern_map.items():
        matches = pattern.findall(fixed_text)
        if matches:
            count = len(matches)
            substitutions.append({
                "original": original,
                "neutral": neutral,
                "category": category,
                "count": count,
            })
            # Perform case-preserving replacement
            def _replace(match: re.Match) -> str:
                matched = match.group(0)
                # Preserve casing: ALL CAPS, Title Case, or lowercase
                if matched.isupper():
                    return neutral.upper()
                if matched[0].isupper():
                    return neutral[0].upper() + neutral[1:]
                return neutral

            fixed_text = pattern.sub(_replace, fixed_text)

    has_bias = len(substitutions) > 0

    if has_bias:
        logger.info(
            "Gender bias check found %d substitution(s): %s",
            len(substitutions),
            [(s["original"], s["neutral"]) for s in substitutions],
        )

    return {
        "has_bias": has_bias,
        "substitutions": substitutions,
        "fixed_text": fixed_text,
    }
