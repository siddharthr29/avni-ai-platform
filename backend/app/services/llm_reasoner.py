"""LLM Reasoner — infer missing semantic properties for SRS form fields.

Takes parsed SRSFormField objects and uses domain reasoning (deterministic rules
+ optional LLM fallback) to infer properties that human specifiers normally fill
manually: allowNegativeValue, allowDecimalValue, allowFutureDate, absolute
ranges, and units.

Two modes:
  - **Deterministic** (fast, no LLM): rules-based dictionary for 60+ common
    health/development fields.
  - **LLM** (slower, smarter): batch-sends unknown fields to the LLM for
    domain-informed inference.

Enrichment is NON-DESTRUCTIVE — only fills properties that are None/missing.
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from app.models.schemas import SRSFormField

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic rules dictionary
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldRule:
    """Known enrichment properties for a common field pattern."""

    allow_negative: bool = False
    allow_decimal: bool = False
    allow_future_date: bool | None = None  # None = not a date field
    low_absolute: float | None = None
    high_absolute: float | None = None
    unit: str | None = None


# Keys are lowercase field-name patterns. Matching is done by checking whether
# the normalised field name *contains* the pattern key (longest match wins).
# This lets "Weight of child" match the "weight" rule, while
# "Birth weight" matches the more specific "birth weight" rule.

_FIELD_RULES: dict[str, FieldRule] = {
    # --- Anthropometry ---
    "birth weight": FieldRule(
        allow_decimal=True, low_absolute=0.5, high_absolute=6.0, unit="kg",
    ),
    "weight": FieldRule(
        allow_decimal=True, low_absolute=0, high_absolute=200, unit="kg",
    ),
    "height": FieldRule(
        allow_decimal=True, low_absolute=0, high_absolute=250, unit="cm",
    ),
    "length": FieldRule(
        allow_decimal=True, low_absolute=0, high_absolute=250, unit="cm",
    ),
    "bmi": FieldRule(
        allow_decimal=True, low_absolute=5, high_absolute=60, unit="kg/m2",
    ),
    "muac": FieldRule(
        allow_decimal=True, low_absolute=5, high_absolute=40, unit="cm",
    ),
    "mid upper arm circumference": FieldRule(
        allow_decimal=True, low_absolute=5, high_absolute=40, unit="cm",
    ),
    "head circumference": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=60, unit="cm",
    ),
    "chest circumference": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=130, unit="cm",
    ),
    "waist circumference": FieldRule(
        allow_decimal=True, low_absolute=30, high_absolute=200, unit="cm",
    ),
    "abdominal girth": FieldRule(
        allow_decimal=True, low_absolute=30, high_absolute=200, unit="cm",
    ),

    # --- Vitals ---
    "temperature": FieldRule(
        allow_decimal=True, low_absolute=90, high_absolute=110, unit="\u00b0F",
    ),
    "body temperature": FieldRule(
        allow_decimal=True, low_absolute=90, high_absolute=110, unit="\u00b0F",
    ),
    "systolic": FieldRule(
        allow_decimal=False, low_absolute=50, high_absolute=260, unit="mmHg",
    ),
    "systolic blood pressure": FieldRule(
        allow_decimal=False, low_absolute=50, high_absolute=260, unit="mmHg",
    ),
    "diastolic": FieldRule(
        allow_decimal=False, low_absolute=30, high_absolute=160, unit="mmHg",
    ),
    "diastolic blood pressure": FieldRule(
        allow_decimal=False, low_absolute=30, high_absolute=160, unit="mmHg",
    ),
    "pulse": FieldRule(
        allow_decimal=False, low_absolute=30, high_absolute=200, unit="bpm",
    ),
    "pulse rate": FieldRule(
        allow_decimal=False, low_absolute=30, high_absolute=200, unit="bpm",
    ),
    "heart rate": FieldRule(
        allow_decimal=False, low_absolute=30, high_absolute=200, unit="bpm",
    ),
    "respiratory rate": FieldRule(
        allow_decimal=False, low_absolute=5, high_absolute=60, unit="/min",
    ),
    "spo2": FieldRule(
        allow_decimal=False, low_absolute=50, high_absolute=100, unit="%",
    ),
    "oxygen saturation": FieldRule(
        allow_decimal=False, low_absolute=50, high_absolute=100, unit="%",
    ),

    # --- Haematology / Lab ---
    "hemoglobin": FieldRule(
        allow_decimal=True, low_absolute=2, high_absolute=20, unit="g/dL",
    ),
    "haemoglobin": FieldRule(
        allow_decimal=True, low_absolute=2, high_absolute=20, unit="g/dL",
    ),
    "hb": FieldRule(
        allow_decimal=True, low_absolute=2, high_absolute=20, unit="g/dL",
    ),
    "blood sugar": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=500, unit="mg/dL",
    ),
    "blood glucose": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=500, unit="mg/dL",
    ),
    "random blood sugar": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=500, unit="mg/dL",
    ),
    "fasting blood sugar": FieldRule(
        allow_decimal=True, low_absolute=20, high_absolute=500, unit="mg/dL",
    ),
    "hba1c": FieldRule(
        allow_decimal=True, low_absolute=3, high_absolute=15, unit="%",
    ),
    "platelet": FieldRule(
        allow_decimal=False, low_absolute=10000, high_absolute=500000, unit="cells/mcL",
    ),
    "wbc": FieldRule(
        allow_decimal=True, low_absolute=1000, high_absolute=30000, unit="cells/mcL",
    ),
    "rbc": FieldRule(
        allow_decimal=True, low_absolute=1, high_absolute=8, unit="million/mcL",
    ),
    "creatinine": FieldRule(
        allow_decimal=True, low_absolute=0.1, high_absolute=15, unit="mg/dL",
    ),
    "bilirubin": FieldRule(
        allow_decimal=True, low_absolute=0, high_absolute=30, unit="mg/dL",
    ),
    "albumin": FieldRule(
        allow_decimal=True, low_absolute=1, high_absolute=6, unit="g/dL",
    ),
    "urea": FieldRule(
        allow_decimal=True, low_absolute=5, high_absolute=200, unit="mg/dL",
    ),
    "esr": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=120, unit="mm/hr",
    ),

    # --- MCH / Obstetric ---
    "fundal height": FieldRule(
        allow_decimal=True, low_absolute=10, high_absolute=50, unit="cm",
    ),
    "uterine height": FieldRule(
        allow_decimal=True, low_absolute=10, high_absolute=50, unit="cm",
    ),
    "gestational age": FieldRule(
        allow_decimal=True, low_absolute=1, high_absolute=45, unit="weeks",
    ),
    "gravida": FieldRule(
        allow_decimal=False, low_absolute=1, high_absolute=15,
    ),
    "parity": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=15,
    ),
    "para": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=15,
    ),
    "number of live births": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=15,
    ),
    "number of still births": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=15,
    ),
    "number of abortions": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=15,
    ),
    "apgar score": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=10,
    ),

    # --- Demographics / Age ---
    "age": FieldRule(
        allow_decimal=True, low_absolute=0, high_absolute=120, unit="years",
    ),
    "age in years": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=120, unit="years",
    ),
    "age in months": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=1440, unit="months",
    ),
    "age at marriage": FieldRule(
        allow_decimal=False, low_absolute=10, high_absolute=100, unit="years",
    ),

    # --- Counts (integer, non-negative) ---
    "number of children": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=20,
    ),
    "number of doses": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=10,
    ),
    "number of anc visits": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=20,
    ),
    "number of family members": FieldRule(
        allow_decimal=False, low_absolute=1, high_absolute=50,
    ),
    "number of pregnancies": FieldRule(
        allow_decimal=False, low_absolute=0, high_absolute=20,
    ),

    # --- Date fields ---
    "date of birth": FieldRule(allow_future_date=False),
    "dob": FieldRule(allow_future_date=False),
    "date of marriage": FieldRule(allow_future_date=False),
    "date of death": FieldRule(allow_future_date=False),
    "date of registration": FieldRule(allow_future_date=False),
    "date of visit": FieldRule(allow_future_date=False),
    "last menstrual period": FieldRule(allow_future_date=False),
    "lmp": FieldRule(allow_future_date=False),
    "date of delivery": FieldRule(allow_future_date=False),
    "expected date of delivery": FieldRule(allow_future_date=True),
    "edd": FieldRule(allow_future_date=True),
    "expected delivery date": FieldRule(allow_future_date=True),
    "next visit date": FieldRule(allow_future_date=True),
    "follow up date": FieldRule(allow_future_date=True),
    "due date": FieldRule(allow_future_date=True),
}

# Patterns for heuristic count detection (when no dictionary match)
_COUNT_PATTERNS = re.compile(
    r"^(number of|no\.? of|count of|total)\b", re.IGNORECASE
)

# Data types that should never get numeric enrichment
_NON_NUMERIC_TYPES = frozenset({
    "Coded", "Text", "Notes", "Image", "ImageV2", "Video", "Audio",
    "File", "PhoneNumber", "Id", "NA", "Subject", "Location",
    "GroupAffiliation", "Duration", "QuestionGroup",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return re.sub(r"\s+", " ", name.strip().lower())


def _find_rule(name: str) -> FieldRule | None:
    """Find the best matching rule for a field name (longest pattern wins)."""
    normalised = _normalise_name(name)
    if not normalised:
        return None

    best_match: str | None = None
    best_length = 0

    for pattern in _FIELD_RULES:
        if pattern in normalised and len(pattern) > best_length:
            best_match = pattern
            best_length = len(pattern)

    return _FIELD_RULES[best_match] if best_match else None


def _get_key_value(kv_list: list[dict[str, Any]], key: str) -> Any | None:
    """Get a value from a keyValues list by key, or None if missing."""
    for item in kv_list:
        if item.get("key") == key:
            return item.get("value")
    return None


def _set_key_value(kv_list: list[dict[str, Any]], key: str, value: Any) -> None:
    """Set a value in a keyValues list (append if not present)."""
    for item in kv_list:
        if item.get("key") == key:
            return  # Already set — non-destructive
    kv_list.append({"key": key, "value": value})


def _is_numeric_type(data_type: str) -> bool:
    """Check whether the Avni data type is numeric."""
    return data_type == "Numeric"


def _is_date_type(data_type: str) -> bool:
    """Check whether the Avni data type is date-like."""
    return data_type in ("Date", "DateTime")


# ---------------------------------------------------------------------------
# Deterministic enrichment
# ---------------------------------------------------------------------------

def _enrich_field_deterministic(field: SRSFormField) -> bool:
    """Apply deterministic rules to a single field.

    Returns True if the field was enriched (any property set).
    """
    data_type = field.dataType or ""
    enriched = False

    # Skip empty names and non-enrichable types
    if not field.name or not field.name.strip():
        return False
    if data_type in _NON_NUMERIC_TYPES:
        return False

    # Ensure keyValues list exists
    if field.keyValues is None:
        field.keyValues = []

    rule = _find_rule(field.name)

    # --- Numeric fields ---
    if _is_numeric_type(data_type):
        # allowNegativeValue: default False for all numeric fields
        if _get_key_value(field.keyValues, "allowNegativeValue") is None:
            allow_neg = rule.allow_negative if rule else False
            _set_key_value(field.keyValues, "allowNegativeValue", allow_neg)
            enriched = True

        # allowDecimalValue
        if _get_key_value(field.keyValues, "allowDecimalValue") is None:
            if rule is not None:
                _set_key_value(field.keyValues, "allowDecimalValue", rule.allow_decimal)
                enriched = True
            elif _COUNT_PATTERNS.search(field.name):
                # Heuristic: "Number of X" fields are always integers
                _set_key_value(field.keyValues, "allowDecimalValue", False)
                enriched = True

        # Absolute ranges
        if rule is not None:
            if field.lowAbsolute is None and rule.low_absolute is not None:
                field.lowAbsolute = rule.low_absolute
                enriched = True
            if field.highAbsolute is None and rule.high_absolute is not None:
                field.highAbsolute = rule.high_absolute
                enriched = True

        # Unit
        if field.unit is None and rule is not None and rule.unit is not None:
            field.unit = rule.unit
            enriched = True

    # --- Date fields ---
    elif _is_date_type(data_type):
        if _get_key_value(field.keyValues, "allowFutureDate") is None:
            if rule is not None and rule.allow_future_date is not None:
                _set_key_value(field.keyValues, "allowFutureDate", rule.allow_future_date)
                enriched = True
            else:
                # Default: dates cannot be in the future (safe default)
                _set_key_value(field.keyValues, "allowFutureDate", False)
                enriched = True

    return enriched


# ---------------------------------------------------------------------------
# LLM-based enrichment
# ---------------------------------------------------------------------------

_LLM_SYSTEM_PROMPT = """You are a health/development domain expert helping configure data collection forms for the Avni platform. For each field, infer reasonable semantic properties based on the field name and data type.

You MUST respond with ONLY a valid JSON array. No markdown, no explanation, no code fences.

For each field in the input array, return an object with:
- "name": the exact field name (unchanged)
- "allowNegativeValue": boolean (for Numeric fields only — can the value be negative?)
- "allowDecimalValue": boolean (for Numeric fields only — can the value have decimals?)
- "allowFutureDate": boolean (for Date fields only — can the date be in the future?)
- "lowAbsolute": number or null (for Numeric fields — physiologically reasonable minimum)
- "highAbsolute": number or null (for Numeric fields — physiologically reasonable maximum)
- "unit": string or null (for Numeric fields — standard unit of measurement)

Rules:
- Count fields (number of X, total X) → allowDecimalValue=false, allowNegativeValue=false
- Measurement fields (weight, height) → allowDecimalValue=true, allowNegativeValue=false
- Past events (date of birth, date of death) → allowFutureDate=false
- Future events (expected delivery date, next visit) → allowFutureDate=true
- For fields you cannot determine, use null for numeric ranges and conservative defaults for booleans
- Only include properties relevant to the data type (no allowFutureDate for Numeric fields)"""


async def _enrich_fields_llm(fields: list[SRSFormField]) -> dict[str, dict[str, Any]]:
    """Send a batch of unknown fields to the LLM for enrichment.

    Returns a dict mapping field name -> enrichment properties.
    """
    from app.services.claude_client import claude_client

    # Build the prompt with field details
    field_descriptions = []
    for f in fields:
        desc = {"name": f.name, "dataType": f.dataType}
        if f.type:
            desc["type"] = f.type
        field_descriptions.append(desc)

    user_message = (
        "Infer semantic properties for these form fields:\n\n"
        + json.dumps(field_descriptions, indent=2)
    )

    try:
        response = await claude_client.complete(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=_LLM_SYSTEM_PROMPT,
        )

        # Parse JSON from the response — handle potential markdown fences
        text = response.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        enrichments = json.loads(text)
        if not isinstance(enrichments, list):
            logger.warning("LLM returned non-list response, ignoring")
            return {}

        result: dict[str, dict[str, Any]] = {}
        for item in enrichments:
            if isinstance(item, dict) and "name" in item:
                result[item["name"]] = item
        return result

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse LLM enrichment response as JSON: %s", e)
        return {}
    except Exception as e:
        logger.error("LLM enrichment failed: %s", e, exc_info=True)
        return {}


def _apply_llm_enrichment(field: SRSFormField, enrichment: dict[str, Any]) -> bool:
    """Apply LLM-inferred enrichment to a field. Non-destructive.

    Returns True if any property was set.
    """
    data_type = field.dataType or ""
    if data_type in _NON_NUMERIC_TYPES:
        return False

    if field.keyValues is None:
        field.keyValues = []

    enriched = False

    if _is_numeric_type(data_type):
        # allowNegativeValue
        if (_get_key_value(field.keyValues, "allowNegativeValue") is None
                and "allowNegativeValue" in enrichment
                and enrichment["allowNegativeValue"] is not None):
            _set_key_value(field.keyValues, "allowNegativeValue", bool(enrichment["allowNegativeValue"]))
            enriched = True

        # allowDecimalValue
        if (_get_key_value(field.keyValues, "allowDecimalValue") is None
                and "allowDecimalValue" in enrichment
                and enrichment["allowDecimalValue"] is not None):
            _set_key_value(field.keyValues, "allowDecimalValue", bool(enrichment["allowDecimalValue"]))
            enriched = True

        # Absolute ranges
        if field.lowAbsolute is None and enrichment.get("lowAbsolute") is not None:
            try:
                field.lowAbsolute = float(enrichment["lowAbsolute"])
                enriched = True
            except (ValueError, TypeError):
                pass

        if field.highAbsolute is None and enrichment.get("highAbsolute") is not None:
            try:
                field.highAbsolute = float(enrichment["highAbsolute"])
                enriched = True
            except (ValueError, TypeError):
                pass

        # Unit
        if field.unit is None and enrichment.get("unit") is not None:
            field.unit = str(enrichment["unit"])
            enriched = True

    elif _is_date_type(data_type):
        if (_get_key_value(field.keyValues, "allowFutureDate") is None
                and "allowFutureDate" in enrichment
                and enrichment["allowFutureDate"] is not None):
            _set_key_value(field.keyValues, "allowFutureDate", bool(enrichment["allowFutureDate"]))
            enriched = True

    return enriched


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def enrich_fields(
    fields: list[SRSFormField],
    use_llm: bool = True,
) -> list[SRSFormField]:
    """Enrich SRS form fields with inferred semantic properties.

    Args:
        fields: List of SRSFormField objects to enrich.
        use_llm: If True, fields not covered by deterministic rules are sent
                 to the LLM for inference. If False, only deterministic rules
                 are applied.

    Returns:
        The same list of fields (mutated in place), with missing properties
        filled in. Existing values are NEVER overwritten.
    """
    if not fields:
        return fields

    deterministic_count = 0
    needs_llm: list[SRSFormField] = []

    for field in fields:
        if not field.name or not field.name.strip():
            logger.debug("Skipping field with empty name")
            continue

        # Check if a known rule exists BEFORE applying defaults
        has_rule = _find_rule(field.name) is not None

        was_enriched = _enrich_field_deterministic(field)
        if was_enriched:
            deterministic_count += 1

        # Send to LLM if no deterministic rule matched (even if defaults were applied)
        if not has_rule:
            data_type = field.dataType or ""
            if data_type not in _NON_NUMERIC_TYPES:
                needs_llm.append(field)

    logger.info(
        "Deterministic enrichment: %d/%d fields enriched",
        deterministic_count,
        len(fields),
    )

    # LLM batch enrichment for unknown fields
    if use_llm and needs_llm:
        logger.info(
            "Sending %d unknown fields to LLM for enrichment",
            len(needs_llm),
        )
        llm_results = await _enrich_fields_llm(needs_llm)
        llm_count = 0
        for field in needs_llm:
            enrichment = llm_results.get(field.name, {})
            if enrichment and _apply_llm_enrichment(field, enrichment):
                llm_count += 1
        logger.info("LLM enrichment: %d/%d fields enriched", llm_count, len(needs_llm))

    return fields
