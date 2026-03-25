"""Convert natural-language showWhen/hideWhen conditions into Avni declarative skip logic rules.

The SRS parser extracts showWhen/hideWhen conditions from Excel columns and stores
them as raw strings in keyValues.  This service converts those strings into real
Avni ViewFilter declarative rules that the Avni rule engine can evaluate.

Pipeline:
  1. **parse_condition** -- regex-based NLP parser (12+ patterns) with LLM fallback
  2. **generate_skip_logic_rule** -- converts a SkipCondition + concepts into a
     declarative rule JSON structure
  3. **generate_skip_logic_for_bundle** -- batch-processes an entire bundle directory,
     scanning all form JSON files for showWhen/hideWhen keyValues and attaching
     declarativeRule to matching form elements
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SkipCondition:
    """Structured representation of a parsed skip-logic condition."""

    trigger_field: str  # e.g. "Pregnancy Status"
    operator: str  # equals, not_equals, greater_than, less_than, etc.
    value: str | None  # e.g. "Yes", "3", None (for is_not_empty / is_empty)
    action: str  # "show" or "hide"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Condition patterns -- order matters; first match wins
# ---------------------------------------------------------------------------

# Each entry is (compiled_regex, operator, action_override).
# Groups: 1 = field name, 2 = value (optional).
# action_override: "show", "hide", or None (inferred from surrounding text).

_CONDITION_PATTERNS: list[tuple[re.Pattern[str], str, str | None]] = [
    # --- Hide patterns (must come before generic "if X is Y") ---
    # "If [Field] is [Value], hide" / "hide if [Field] is [Value]"
    (
        re.compile(
            r"(?:hide\s+(?:when|if|this)?\s*)?(?:if|when)\s+\[?(.+?)\]?\s+(?:is|=|==)\s+\[?(.+?)\]?[,\s]*hide",
            re.IGNORECASE,
        ),
        "equals",
        "hide",
    ),
    (
        re.compile(
            r"hide\s+(?:when|if)\s+\[?(.+?)\]?\s+(?:is|=|==)\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "equals",
        "hide",
    ),
    # --- "is not empty" / "is filled" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+(?:is\s+not\s+empty|is\s+filled|has\s+(?:a\s+)?value|is\s+not\s+blank)",
            re.IGNORECASE,
        ),
        "is_not_empty",
        None,
    ),
    # --- "is empty" / "is blank" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+(?:is\s+empty|is\s+blank|has\s+no\s+value|is\s+not\s+filled)",
            re.IGNORECASE,
        ),
        "is_empty",
        None,
    ),
    # --- "is not [Value]" / "!= [Value]" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+(?:is\s+not|!=|<>|does\s+not\s+equal)\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "not_equals",
        None,
    ),
    # --- Numeric: "> N", ">= N" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s*(?:>|is\s+greater\s+than|is\s+more\s+than|exceeds)\s*=?\s*\[?(\d+(?:\.\d+)?)\]?",
            re.IGNORECASE,
        ),
        "greater_than",
        None,
    ),
    # --- Numeric: "< N", "<= N" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s*(?:<|is\s+less\s+than|is\s+below)\s*=?\s*\[?(\d+(?:\.\d+)?)\]?",
            re.IGNORECASE,
        ),
        "less_than",
        None,
    ),
    # --- "contains [Value]" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+contains\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "contains",
        None,
    ),
    # --- "is one of [V1, V2, V3]" / "is any of [...]" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+(?:is\s+(?:one|any)\s+of)\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "one_of",
        None,
    ),
    # --- "is between [A] and [B]" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+is\s+between\s+\[?(\d+(?:\.\d+)?)\]?\s+and\s+\[?(\d+(?:\.\d+)?)\]?",
            re.IGNORECASE,
        ),
        "between",
        None,
    ),
    # --- Generic: "If [Field] is [Value]" / "When [Field] = [Value]" ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s+(?:is|=|==|equals)\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "equals",
        None,
    ),
    # --- Bare field reference: "If [Field]" (truthy check) ---
    (
        re.compile(
            r"(?:if|when)\s+\[?(.+?)\]?\s*$",
            re.IGNORECASE,
        ),
        "is_not_empty",
        None,
    ),
]

# Regex to detect whether the surrounding text implies "hide"
_HIDE_INDICATOR = re.compile(r"\bhide\b", re.IGNORECASE)

# Operator → Avni declarative operator mapping
_OPERATOR_MAP: dict[str, str] = {
    "equals": "containsAnswerConceptName",
    "not_equals": "notContainsAnswerConceptName",
    "contains": "containsAnswerConceptName",
    "one_of": "containsAnswerConceptName",
    "is_not_empty": "defined",
    "is_empty": "notDefined",
    "greater_than": "greaterThan",
    "less_than": "lessThan",
    "between": "between",
}


# ---------------------------------------------------------------------------
# Condition parser
# ---------------------------------------------------------------------------


def parse_condition(text: str, context: str = "show") -> SkipCondition | None:
    """Parse a natural-language condition string into a SkipCondition.

    Args:
        text: The raw condition string from the SRS Excel (e.g. "If Age > 18").
        context: "show" if from a showWhen column, "hide" if from hideWhen.

    Returns:
        A SkipCondition if successfully parsed, or None if the text cannot be
        matched against any known pattern.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    for pattern, operator, action_override in _CONDITION_PATTERNS:
        m = pattern.match(cleaned)
        if not m:
            continue

        groups = m.groups()
        field_name = groups[0].strip()

        # Determine value
        if operator in ("is_not_empty", "is_empty"):
            value = None
        elif operator == "between" and len(groups) >= 3:
            # Store as "low,high"
            value = f"{groups[1].strip()},{groups[2].strip()}"
        elif len(groups) >= 2 and groups[1] is not None:
            value = groups[1].strip()
        else:
            value = None

        # Determine action
        if action_override:
            action = action_override
        elif context == "hide":
            action = "hide"
        elif _HIDE_INDICATOR.search(cleaned):
            action = "hide"
        else:
            action = "show"

        logger.debug(
            "Parsed condition: field=%s, op=%s, val=%s, action=%s from '%s'",
            field_name, operator, value, action, cleaned,
        )
        return SkipCondition(
            trigger_field=field_name,
            operator=operator,
            value=value,
            action=action,
        )

    logger.warning("No pattern matched for condition: '%s'", cleaned)
    return None


async def parse_condition_with_llm_fallback(
    text: str,
    context: str = "show",
) -> SkipCondition | None:
    """Parse condition with regex first, falling back to LLM for complex cases.

    Returns None if both regex and LLM fail.
    """
    # Try regex first
    result = parse_condition(text, context)
    if result is not None:
        return result

    # LLM fallback
    try:
        from app.services.claude_client import claude_client

        prompt = (
            "Parse this Avni form skip-logic condition into structured JSON.\n"
            f"Condition text: \"{text}\"\n"
            f"Context: This is from a {'showWhen' if context == 'show' else 'hideWhen'} column.\n\n"
            "Return ONLY a JSON object with these fields:\n"
            '  "trigger_field": "the field name being checked",\n'
            '  "operator": one of "equals", "not_equals", "greater_than", "less_than", '
            '"is_not_empty", "is_empty", "contains", "one_of", "between",\n'
            '  "value": "the value being compared" or null,\n'
            '  "action": "show" or "hide"\n\n'
            "Return ONLY the JSON, no explanation."
        )
        response = await claude_client.complete(
            messages=[{"role": "user", "content": prompt}],
            system_prompt="You are a precise JSON parser. Return only valid JSON.",
        )

        # Extract JSON from response
        json_match = re.search(r"\{[^}]+\}", response)
        if json_match:
            data = json.loads(json_match.group())
            condition = SkipCondition(
                trigger_field=data["trigger_field"],
                operator=data["operator"],
                value=data.get("value"),
                action=data.get("action", context),
            )
            logger.info("LLM parsed condition: %s from '%s'", condition, text)
            return condition

    except Exception:
        logger.warning("LLM fallback failed for condition: '%s'", text, exc_info=True)

    return None


# ---------------------------------------------------------------------------
# Concept lookup
# ---------------------------------------------------------------------------


class ConceptLookup:
    """Resolves concept names and answer UUIDs from a bundle's concepts.json."""

    def __init__(self, concepts: list[dict[str, Any]]) -> None:
        # Index by lowercase name for case-insensitive lookup
        self._by_name: dict[str, dict[str, Any]] = {}
        # Also index answers globally for quick UUID resolution
        self._answers: dict[str, str] = {}  # lowercase name → uuid

        for c in concepts:
            name = c.get("name", "")
            self._by_name[name.lower()] = c
            for ans in c.get("answers", []):
                ans_name = ans.get("name", "")
                if ans_name:
                    self._answers[ans_name.lower()] = ans.get("uuid", "")

    def find_concept(self, name: str) -> dict[str, Any] | None:
        """Find a concept by name (case-insensitive)."""
        return self._by_name.get(name.lower())

    def find_answer_uuid(self, concept_name: str, answer_name: str) -> str | None:
        """Find the UUID for an answer within a specific concept, or globally."""
        concept = self.find_concept(concept_name)
        if concept:
            for ans in concept.get("answers", []):
                if ans.get("name", "").lower() == answer_name.lower():
                    return ans.get("uuid")
        # Global fallback
        return self._answers.get(answer_name.lower())

    def find_concept_uuid(self, name: str) -> str | None:
        """Return the UUID for a concept by name."""
        concept = self.find_concept(name)
        return concept.get("uuid") if concept else None

    def find_concept_data_type(self, name: str) -> str | None:
        """Return the dataType for a concept by name."""
        concept = self.find_concept(name)
        return concept.get("dataType") if concept else None


# ---------------------------------------------------------------------------
# Rule generation
# ---------------------------------------------------------------------------


def _infer_scope(form_type: str | None) -> str:
    """Infer the appropriate scope from a form type."""
    if not form_type:
        return "encounter"
    ft = form_type.lower()
    if "registration" in ft or "individual" in ft:
        return "registration"
    if "enrolment" in ft:
        return "programEnrolment"
    if "exit" in ft:
        return "programExit"
    return "encounter"


def generate_skip_logic_rule(
    condition: SkipCondition,
    concepts: ConceptLookup,
    scope: str = "encounter",
) -> dict[str, Any] | None:
    """Generate an Avni declarative skip-logic rule from a parsed condition.

    Args:
        condition: The parsed skip condition.
        concepts: Concept lookup loaded from the bundle's concepts.json.
        scope: The Avni scope (encounter, programEnrolment, registration, etc.).

    Returns:
        A declarativeRule dict ready to attach to a form element, or None if
        the required concepts/answers could not be resolved.
    """
    trigger_uuid = concepts.find_concept_uuid(condition.trigger_field)
    if not trigger_uuid:
        logger.warning(
            "Cannot generate rule: concept '%s' not found in concepts.json",
            condition.trigger_field,
        )
        return None

    data_type = concepts.find_concept_data_type(condition.trigger_field) or "Coded"
    action_type = "showFormElement" if condition.action == "show" else "hideFormElement"

    # Build the rule based on operator type
    if condition.operator in ("equals", "not_equals", "contains"):
        if not condition.value:
            logger.warning(
                "Cannot generate rule: operator '%s' requires a value for concept '%s'",
                condition.operator, condition.trigger_field,
            )
            return None

        answer_uuid = concepts.find_answer_uuid(condition.trigger_field, condition.value)
        if not answer_uuid:
            logger.warning(
                "Cannot generate rule: answer '%s' not found for concept '%s'",
                condition.value, condition.trigger_field,
            )
            return None

        avni_operator = _OPERATOR_MAP[condition.operator]
        rule = _build_coded_rule(
            scope=scope,
            concept_name=condition.trigger_field,
            concept_uuid=trigger_uuid,
            concept_data_type=data_type,
            operator=avni_operator,
            answer_names=[condition.value],
            answer_uuids=[answer_uuid],
            action_type=action_type,
        )

    elif condition.operator == "one_of":
        if not condition.value:
            return None

        answer_names = [v.strip() for v in condition.value.split(",")]
        answer_uuids = []
        for a_name in answer_names:
            a_uuid = concepts.find_answer_uuid(condition.trigger_field, a_name)
            if not a_uuid:
                logger.warning("Answer '%s' not found for concept '%s'", a_name, condition.trigger_field)
                return None
            answer_uuids.append(a_uuid)

        rule = _build_coded_rule(
            scope=scope,
            concept_name=condition.trigger_field,
            concept_uuid=trigger_uuid,
            concept_data_type=data_type,
            operator="containsAnswerConceptName",
            answer_names=answer_names,
            answer_uuids=answer_uuids,
            action_type=action_type,
        )

    elif condition.operator in ("is_not_empty", "is_empty"):
        avni_operator = _OPERATOR_MAP[condition.operator]
        rule = _build_existence_rule(
            scope=scope,
            concept_name=condition.trigger_field,
            concept_uuid=trigger_uuid,
            concept_data_type=data_type,
            operator=avni_operator,
            action_type=action_type,
        )

    elif condition.operator in ("greater_than", "less_than"):
        if not condition.value:
            return None
        avni_operator = _OPERATOR_MAP[condition.operator]
        rule = _build_numeric_rule(
            scope=scope,
            concept_name=condition.trigger_field,
            concept_uuid=trigger_uuid,
            operator=avni_operator,
            value=condition.value,
            action_type=action_type,
        )

    elif condition.operator == "between":
        if not condition.value or "," not in condition.value:
            return None
        parts = condition.value.split(",")
        rule = _build_between_rule(
            scope=scope,
            concept_name=condition.trigger_field,
            concept_uuid=trigger_uuid,
            low=parts[0].strip(),
            high=parts[1].strip(),
            action_type=action_type,
        )

    else:
        logger.warning("Unsupported operator '%s' for rule generation", condition.operator)
        return None

    return rule


def _build_coded_rule(
    *,
    scope: str,
    concept_name: str,
    concept_uuid: str,
    concept_data_type: str,
    operator: str,
    answer_names: list[str],
    answer_uuids: list[str],
    action_type: str,
) -> dict[str, Any]:
    return {
        "declarativeRule": [
            {
                "conditions": [
                    {
                        "compoundRule": {
                            "conjunction": "And",
                            "rules": [
                                {
                                    "lhs": {
                                        "type": "concept",
                                        "scope": scope,
                                        "conceptName": concept_name,
                                        "conceptUuid": concept_uuid,
                                        "conceptDataType": concept_data_type,
                                    },
                                    "operator": operator,
                                    "rhs": {
                                        "type": "answerConcept",
                                        "answerConceptNames": answer_names,
                                        "answerConceptUuids": answer_uuids,
                                    },
                                }
                            ],
                        }
                    }
                ],
                "actions": [{"actionType": action_type}],
            }
        ]
    }


def _build_existence_rule(
    *,
    scope: str,
    concept_name: str,
    concept_uuid: str,
    concept_data_type: str,
    operator: str,
    action_type: str,
) -> dict[str, Any]:
    return {
        "declarativeRule": [
            {
                "conditions": [
                    {
                        "compoundRule": {
                            "conjunction": "And",
                            "rules": [
                                {
                                    "lhs": {
                                        "type": "concept",
                                        "scope": scope,
                                        "conceptName": concept_name,
                                        "conceptUuid": concept_uuid,
                                        "conceptDataType": concept_data_type,
                                    },
                                    "operator": operator,
                                    "rhs": {
                                        "type": "value",
                                        "value": None,
                                    },
                                }
                            ],
                        }
                    }
                ],
                "actions": [{"actionType": action_type}],
            }
        ]
    }


def _build_numeric_rule(
    *,
    scope: str,
    concept_name: str,
    concept_uuid: str,
    operator: str,
    value: str,
    action_type: str,
) -> dict[str, Any]:
    return {
        "declarativeRule": [
            {
                "conditions": [
                    {
                        "compoundRule": {
                            "conjunction": "And",
                            "rules": [
                                {
                                    "lhs": {
                                        "type": "concept",
                                        "scope": scope,
                                        "conceptName": concept_name,
                                        "conceptUuid": concept_uuid,
                                        "conceptDataType": "Numeric",
                                    },
                                    "operator": operator,
                                    "rhs": {
                                        "type": "value",
                                        "value": value,
                                    },
                                }
                            ],
                        }
                    }
                ],
                "actions": [{"actionType": action_type}],
            }
        ]
    }


def _build_between_rule(
    *,
    scope: str,
    concept_name: str,
    concept_uuid: str,
    low: str,
    high: str,
    action_type: str,
) -> dict[str, Any]:
    return {
        "declarativeRule": [
            {
                "conditions": [
                    {
                        "compoundRule": {
                            "conjunction": "And",
                            "rules": [
                                {
                                    "lhs": {
                                        "type": "concept",
                                        "scope": scope,
                                        "conceptName": concept_name,
                                        "conceptUuid": concept_uuid,
                                        "conceptDataType": "Numeric",
                                    },
                                    "operator": "greaterThan",
                                    "rhs": {
                                        "type": "value",
                                        "value": low,
                                    },
                                },
                                {
                                    "lhs": {
                                        "type": "concept",
                                        "scope": scope,
                                        "conceptName": concept_name,
                                        "conceptUuid": concept_uuid,
                                        "conceptDataType": "Numeric",
                                    },
                                    "operator": "lessThan",
                                    "rhs": {
                                        "type": "value",
                                        "value": high,
                                    },
                                },
                            ],
                        }
                    }
                ],
                "actions": [{"actionType": action_type}],
            }
        ]
    }


# ---------------------------------------------------------------------------
# Batch processor
# ---------------------------------------------------------------------------


def _load_concepts_from_bundle(bundle_dir: str) -> ConceptLookup | None:
    """Load concepts.json from a bundle directory."""
    concepts_path = Path(bundle_dir) / "concepts.json"
    if not concepts_path.is_file():
        logger.error("concepts.json not found in bundle: %s", bundle_dir)
        return None
    try:
        with open(concepts_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            # Some bundles wrap concepts in {"concepts": [...]}
            data = data.get("concepts", [data])
        if not isinstance(data, list):
            data = [data]
        return ConceptLookup(data)
    except Exception:
        logger.error("Failed to load concepts.json from %s", bundle_dir, exc_info=True)
        return None


def _find_form_files(bundle_dir: str) -> list[Path]:
    """Find all form JSON files in a bundle directory."""
    bundle_path = Path(bundle_dir)
    form_files: list[Path] = []

    # Check common form locations
    for pattern in ["forms/*.json", "*.json"]:
        for p in bundle_path.glob(pattern):
            if p.name != "concepts.json" and p.stem != "concepts":
                # Peek to see if it looks like a form file
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if isinstance(data, dict) and "formElementGroups" in data:
                        form_files.append(p)
                    elif isinstance(data, list):
                        # Array of forms
                        if data and isinstance(data[0], dict) and "formElementGroups" in data[0]:
                            form_files.append(p)
                except Exception:
                    continue

    return form_files


def _extract_key_value(key_values: list[dict], key: str) -> str | None:
    """Extract a value from a keyValues list by key name."""
    for kv in key_values:
        if kv.get("key") == key:
            return kv.get("value")
    return None


async def generate_skip_logic_for_bundle(bundle_dir: str) -> dict[str, Any]:
    """Scan a bundle directory and generate skip-logic rules for all form elements.

    For each form element that has a showWhen or hideWhen keyValue, this function:
      1. Parses the condition text into a SkipCondition
      2. Looks up concept UUIDs from concepts.json
      3. Generates a declarativeRule and attaches it to the form element
      4. Writes the updated form JSON back to disk

    Returns:
        Summary dict with keys: rules_generated, rules_failed, parse_failed, details.
    """
    result: dict[str, Any] = {
        "rules_generated": 0,
        "rules_failed": 0,
        "parse_failed": 0,
        "details": [],
    }

    concepts = _load_concepts_from_bundle(bundle_dir)
    if concepts is None:
        result["details"].append({
            "error": "concepts.json not found or invalid",
            "bundle_dir": bundle_dir,
        })
        return result

    form_files = _find_form_files(bundle_dir)
    if not form_files:
        logger.info("No form files found in bundle: %s", bundle_dir)
        return result

    for form_path in form_files:
        try:
            with open(form_path, "r", encoding="utf-8") as f:
                form_data = json.load(f)
        except Exception:
            logger.error("Failed to read form file: %s", form_path, exc_info=True)
            continue

        # Handle both single form and array of forms
        forms = form_data if isinstance(form_data, list) else [form_data]
        modified = False

        for form in forms:
            form_type = form.get("formType")
            scope = _infer_scope(form_type)

            for group in form.get("formElementGroups", []):
                for element in group.get("formElements", []):
                    key_values = element.get("keyValues", [])
                    if not key_values:
                        continue

                    element_name = element.get("name", "<unknown>")

                    for kv_key, context in [("showWhen", "show"), ("hideWhen", "hide")]:
                        condition_text = _extract_key_value(key_values, kv_key)
                        if not condition_text:
                            continue

                        # Parse the condition
                        condition = await parse_condition_with_llm_fallback(
                            condition_text, context
                        )
                        if condition is None:
                            result["parse_failed"] += 1
                            result["details"].append({
                                "element": element_name,
                                "condition_text": condition_text,
                                "status": "parse_failed",
                                "source": kv_key,
                            })
                            continue

                        # Generate the rule
                        rule = generate_skip_logic_rule(condition, concepts, scope)
                        if rule is None:
                            result["rules_failed"] += 1
                            result["details"].append({
                                "element": element_name,
                                "condition_text": condition_text,
                                "condition": condition.to_dict(),
                                "status": "rule_generation_failed",
                                "source": kv_key,
                            })
                            continue

                        # Attach the rule to the form element
                        element["rule"] = json.dumps(rule)
                        modified = True
                        result["rules_generated"] += 1
                        result["details"].append({
                            "element": element_name,
                            "condition_text": condition_text,
                            "condition": condition.to_dict(),
                            "status": "success",
                            "source": kv_key,
                        })

                        logger.info(
                            "Generated %s rule for '%s' from %s='%s'",
                            condition.action, element_name, kv_key, condition_text,
                        )

        # Write updated form back
        if modified:
            try:
                output = form_data if isinstance(form_data, list) else forms[0]
                with open(form_path, "w", encoding="utf-8") as f:
                    json.dump(output, f, indent=2, ensure_ascii=False)
                logger.info("Updated form file with skip-logic rules: %s", form_path)
            except Exception:
                logger.error("Failed to write updated form: %s", form_path, exc_info=True)

    logger.info(
        "Skip logic generation complete: %d generated, %d failed, %d unparseable",
        result["rules_generated"],
        result["rules_failed"],
        result["parse_failed"],
    )
    return result
