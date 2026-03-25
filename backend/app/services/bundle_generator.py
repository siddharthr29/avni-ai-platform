import json
import logging
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Any

from app.config import settings
from app.models.schemas import (
    BundleStatus,
    BundleStatusType,
    SRSData,
    SRSFormDefinition,
    SRSFormField,
    SRSFormGroup,
)

logger = logging.getLogger(__name__)

# Keys whose numeric values should always have .0 suffix (float format in Avni)
FLOAT_KEYS = {"level", "displayOrder", "order", "lowAbsolute", "highAbsolute", "lowNormal", "highNormal"}

# In-memory store for bundle generation status
_bundle_store: dict[str, BundleStatus] = {}


def _new_uuid() -> str:
    return str(uuid.uuid4())


class UUIDRegistry:
    """Ensures concept reuse across forms by caching UUIDs keyed by logical name.

    On construction, loads the standard UUID registry from the knowledge base
    training data (``app/knowledge/data/uuid_registry.json``).  When a concept
    key of the form ``concept:<name>`` is requested and *<name>* matches a
    known answer in the registry, the production UUID is returned instead of
    generating a random one.  This keeps bundles consistent with production
    Avni deployments for common answers like Yes, No, Male, Female, SC, ST, etc.
    """

    def __init__(self) -> None:
        self._cache: dict[str, str] = {}
        self._standard_uuids: dict[str, str] = {}
        self._load_standard_uuids()

    def _load_standard_uuids(self) -> None:
        """Load known answer UUIDs from the training-data registry."""
        registry_path = (
            Path(__file__).resolve().parent.parent
            / "knowledge" / "data" / "uuid_registry.json"
        )
        if not registry_path.is_file():
            logger.warning(
                "uuid_registry.json not found at %s; "
                "all UUIDs will be randomly generated",
                registry_path,
            )
            return
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._standard_uuids = dict(data)
                logger.info(
                    "Loaded %d standard UUIDs from uuid_registry.json",
                    len(self._standard_uuids),
                )
        except Exception:
            logger.warning(
                "Failed to load uuid_registry.json", exc_info=True
            )

    # Fixed namespace for deterministic UUID generation (UUID5)
    _NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

    def stable_uuid(self, key: str) -> str:
        if key not in self._cache:
            # Check if this is a concept key that matches a known answer
            if key.startswith("concept:"):
                concept_name = key[len("concept:"):]
                standard = self._standard_uuids.get(concept_name)
                if standard:
                    self._cache[key] = standard
                    return self._cache[key]
            # Deterministic UUID based on key — same entity always gets same UUID
            self._cache[key] = str(uuid.uuid5(self._NAMESPACE, key))
        return self._cache[key]

    def new_uuid(self) -> str:
        return _new_uuid()


class ConceptManager:
    """Manages concept creation and deduplication across all forms."""

    def __init__(self, registry: UUIDRegistry) -> None:
        self._registry = registry
        self._concepts: dict[str, dict[str, Any]] = {}

    def get_or_create(
        self,
        name: str,
        data_type: str,
        unit: str | None = None,
        low_absolute: float | None = None,
        high_absolute: float | None = None,
        low_normal: float | None = None,
        high_normal: float | None = None,
    ) -> dict[str, Any]:
        key = f"concept:{name.lower()}"
        if key in self._concepts:
            existing = self._concepts[key]
            # Upgrade NA -> Coded if needed
            if data_type == "Coded" and existing["dataType"] == "NA":
                existing["dataType"] = "Coded"
                if "answers" not in existing:
                    existing["answers"] = []
            if unit and not existing.get("unit"):
                existing["unit"] = unit
            if low_absolute is not None and existing.get("lowAbsolute") is None:
                existing["lowAbsolute"] = low_absolute
            if high_absolute is not None and existing.get("highAbsolute") is None:
                existing["highAbsolute"] = high_absolute
            if low_normal is not None and existing.get("lowNormal") is None:
                existing["lowNormal"] = low_normal
            if high_normal is not None and existing.get("highNormal") is None:
                existing["highNormal"] = high_normal
            return existing

        concept: dict[str, Any] = {
            "name": name,
            "uuid": self._registry.stable_uuid(key),
            "dataType": data_type,
            "active": True,
        }
        if unit:
            concept["unit"] = unit
        if low_absolute is not None:
            concept["lowAbsolute"] = low_absolute
        if high_absolute is not None:
            concept["highAbsolute"] = high_absolute
        if low_normal is not None:
            concept["lowNormal"] = low_normal
        if high_normal is not None:
            concept["highNormal"] = high_normal
        if data_type == "Coded":
            concept["answers"] = []
        self._concepts[key] = concept
        return concept

    def get_or_create_answer(self, name: str) -> dict[str, Any]:
        name = name.strip().rstrip(",").strip()
        key = f"concept:{name.lower()}"
        if key in self._concepts:
            return self._concepts[key]
        concept: dict[str, Any] = {
            "name": name,
            "uuid": self._registry.stable_uuid(key),
            "dataType": "NA",
            "active": True,
        }
        self._concepts[key] = concept
        return concept

    def ensure_coded_with_answers(
        self,
        concept_name: str,
        answer_names: list[str],
        unit: str | None = None,
        low_absolute: float | None = None,
        high_absolute: float | None = None,
        low_normal: float | None = None,
        high_normal: float | None = None,
    ) -> dict[str, Any]:
        concept = self.get_or_create(
            concept_name, "Coded", unit=unit,
            low_absolute=low_absolute, high_absolute=high_absolute,
            low_normal=low_normal, high_normal=high_normal,
        )
        if "answers" not in concept:
            concept["answers"] = []

        existing_answer_names = {a["name"] for a in concept["answers"]}
        for a_name in answer_names:
            if a_name not in existing_answer_names:
                answer_concept = self.get_or_create_answer(a_name)
                concept["answers"].append({
                    "name": a_name,
                    "uuid": answer_concept["uuid"],
                    "order": float(len(concept["answers"])),
                })

        # Re-order
        for i, answer in enumerate(concept["answers"]):
            answer["order"] = float(i)

        return concept

    def all_concepts(self) -> list[dict[str, Any]]:
        """Serialize all concepts to the format expected by avni-server's ConceptContract.

        Key fields per avni-server source:
        - name, uuid, dataType, active, voided (required)
        - keyValues: KeyValues (extends ArrayList<KeyValue>)
        - media: List<ConceptMedia>
        - answers: List<ConceptContract> with dataType, abnormal, unique, voided, active
        - unit, lowAbsolute, highAbsolute, lowNormal, highNormal (for Numeric)

        CRITICAL: Answer concepts MUST also appear as standalone entries with dataType "NA".
        The server resolves answer_concept_id via UUID lookup — if the answer concept
        doesn't exist as a top-level entry, the server throws ConstraintViolationException.
        """
        result = []
        # Track which answer concepts need standalone entries
        answer_concepts_needed: list[dict[str, Any]] = []
        emitted_uuids: set[str] = set()

        for c in self._concepts.values():
            concept: dict[str, Any] = {
                "name": c["name"],
                "uuid": c["uuid"],
                "dataType": c["dataType"],
                "voided": False,
                "active": c.get("active", True),
                "keyValues": c.get("keyValues") or [],
                "media": c.get("media") or [],
            }
            if c.get("unit"):
                concept["unit"] = c["unit"]
            if c.get("lowAbsolute") is not None:
                concept["lowAbsolute"] = c["lowAbsolute"]
            if c.get("highAbsolute") is not None:
                concept["highAbsolute"] = c["highAbsolute"]
            if c.get("lowNormal") is not None:
                concept["lowNormal"] = c["lowNormal"]
            if c.get("highNormal") is not None:
                concept["highNormal"] = c["highNormal"]
            if c["dataType"] == "Coded" and c.get("answers"):
                concept["answers"] = [
                    {
                        "name": a["name"],
                        "uuid": a["uuid"],
                        "order": a["order"],
                        "abnormal": a.get("abnormal", False),
                        "unique": a.get("unique", False),
                        "voided": a.get("voided", False),
                    }
                    for a in c["answers"]
                ]
                # Collect answer concepts that need standalone entries
                for a in c["answers"]:
                    answer_concepts_needed.append({
                        "name": a["name"],
                        "uuid": a["uuid"],
                    })
            result.append(concept)
            emitted_uuids.add(c["uuid"])

        # Emit standalone answer concepts with dataType "NA" for any not already
        # present as top-level concepts. Server requires these for answer_concept_id
        # foreign key resolution.
        for ac in answer_concepts_needed:
            if ac["uuid"] not in emitted_uuids:
                result.append({
                    "name": ac["name"],
                    "uuid": ac["uuid"],
                    "dataType": "NA",
                    "voided": False,
                    "active": True,
                })
                emitted_uuids.add(ac["uuid"])

        return result

    def validate_no_name_collisions(self) -> list[str]:
        """Check that no question concept name collides with an answer concept name.

        Server error C7: If a field name like "Abortion" is also used as a coded answer,
        and they get different UUIDs, the server crashes with BadRequestError.
        With our ConceptManager they share the same UUID (same key), so this is safe
        IF the dataType is consistent. But if a concept is used as both a Coded question
        AND an NA answer, the dataType conflict will cause issues.

        Returns list of collision error messages.
        """
        errors: list[str] = []
        question_concepts: dict[str, str] = {}  # name_lower -> dataType
        answer_names: set[str] = set()

        for c in self._concepts.values():
            name_lower = c["name"].lower()
            if c["dataType"] != "NA":
                question_concepts[name_lower] = c["dataType"]
            if c["dataType"] == "Coded" and c.get("answers"):
                for a in c["answers"]:
                    answer_names.add(a["name"].lower())

        # Check for names that are both questions (non-NA) and answers
        for ans_name in answer_names:
            if ans_name in question_concepts:
                dt = question_concepts[ans_name]
                if dt != "NA" and dt != "Coded":
                    errors.append(
                        f"Concept name collision: '{ans_name}' is used as both "
                        f"a {dt} question concept and a coded answer. "
                        f"The server will reject this with BadRequestError."
                    )
        return errors


def _build_form_element(
    field: SRSFormField,
    display_order: int,
    concepts: ConceptManager,
    registry: UUIDRegistry,
    form_name: str = "",
    rule_injector: RuleInjector | None = None,
    form_def: SRSFormDefinition | None = None,
    all_fields: dict[str, SRSFormField] | None = None,
    ordered_field_names: list[str] | None = None,
) -> dict[str, Any]:
    """Build a single form element from a field definition."""
    concept_data_type = field.dataType

    if field.dataType == "Coded":
        concept = concepts.ensure_coded_with_answers(
            field.name,
            field.options or [],
            unit=field.unit,
            low_absolute=field.lowAbsolute,
            high_absolute=field.highAbsolute,
        )
    else:
        concept = concepts.get_or_create(
            field.name,
            concept_data_type,
            unit=field.unit,
            low_absolute=field.lowAbsolute,
            high_absolute=field.highAbsolute,
        )

    # Build form element concept representation (matches FormElementContract → ConceptContract)
    # Must match known-good bundle: name, uuid, dataType, voided, answers, active, media
    form_concept: dict[str, Any] = {
        "name": concept["name"],
        "uuid": concept["uuid"],
        "dataType": concept["dataType"],
        "voided": False,
        "answers": [],
        "active": True,
        "media": [],
    }

    if concept["dataType"] == "Coded" and concept.get("answers"):
        form_concept["answers"] = [
            {
                "name": a["name"],
                "uuid": a["uuid"],
                "dataType": "NA",
                "voided": False,
                "answers": [],
                "order": a["order"],
                "abnormal": False,
                "unique": False,
                "active": True,
                "media": [],
            }
            for a in concept["answers"]
        ]

    # avni-server FormElementType enum: ONLY "SingleSelect" and "MultiSelect" are valid
    if field.dataType == "Coded" and field.type and field.type.lower() in ("multiselect", "multi"):
        element_type = "MultiSelect"
    else:
        element_type = "SingleSelect"

    element: dict[str, Any] = {
        "name": field.name,
        "uuid": registry.stable_uuid(f"form_element:{form_name}:{field.name}"),
        "keyValues": field.keyValues or [],
        "concept": form_concept,
        "displayOrder": float(display_order),
        "type": element_type,
        "mandatory": field.mandatory,
        "voided": False,
        "rule": "",
        "declarativeRule": None,
        "validFormat": None,
        "parentFormElementUuid": None,
        "documentation": None,
    }

    # Inject skip logic rule from showWhen/hideWhen
    if rule_injector and form_def and all_fields:
        rule_injector.inject_element_rule(
            element, field, form_def, all_fields, ordered_field_names,
        )

    return element


def _build_form(
    form_def: SRSFormDefinition,
    form_uuid: str,
    concepts: ConceptManager,
    registry: UUIDRegistry,
    rule_injector: RuleInjector | None = None,
) -> dict[str, Any]:
    """Build a complete form JSON from a form definition."""
    # Build a lookup of all fields in this form for cross-referencing in rules
    all_fields: dict[str, SRSFormField] = {}
    ordered_field_names: list[str] = []
    for group in form_def.groups:
        for field in group.fields:
            all_fields[field.name] = field
            ordered_field_names.append(field.name)

    form_element_groups = []
    for gi, group in enumerate(form_def.groups):
        elements = []
        for fi, field in enumerate(group.fields):
            elements.append(
                _build_form_element(
                    field, fi + 1, concepts, registry,
                    form_name=form_def.name,
                    rule_injector=rule_injector,
                    form_def=form_def,
                    all_fields=all_fields,
                    ordered_field_names=ordered_field_names,
                )
            )
        form_element_groups.append({
            "uuid": registry.stable_uuid(f"form_element_group:{form_def.name}:{group.name}"),
            "name": group.name,
            "displayOrder": float(gi + 1),
            "display": group.name,
            "voided": False,
            "rule": "",
            "declarativeRule": None,
            "timed": False,
            "startTime": None,
            "stayTime": None,
            "textColour": None,
            "backgroundColour": None,
            "formElements": elements,
        })

    # Generate form-level rules (JS + declarative)
    visit_schedule_rule = ""
    visit_schedule_decl = None
    validation_rule = ""
    validation_decl = None
    if rule_injector:
        visit_schedule_rule, visit_schedule_decl = rule_injector.generate_visit_schedule(form_def)
        validation_rule, validation_decl = rule_injector.generate_validation_rule(form_def)

    form_json: dict[str, Any] = {
        "name": form_def.name,
        "uuid": form_uuid,
        "formType": form_def.formType,
        "decisionRule": "",
        "validationRule": validation_rule or "",
        "visitScheduleRule": visit_schedule_rule or "",
        "checklistsRule": "",
        "editFormRule": "",
        "taskScheduleRule": "",
        "voided": False,
        "decisionConcepts": [],
        "formElementGroups": form_element_groups,
    }

    # Add declarative rule fields when present (same format as Avni webapp rule builder)
    if visit_schedule_decl:
        form_json["visitScheduleDeclarativeRule"] = visit_schedule_decl
    if validation_decl:
        form_json["validationDeclarativeRule"] = validation_decl

    return form_json


# ---------------------------------------------------------------------------
# Rule injection — auto-generate Avni declarative rules + JS from SRS metadata
# ---------------------------------------------------------------------------

def _resolve_field_name(raw: str, field_lookup: dict[str, Any]) -> str | None:
    """Case-insensitive field name resolution."""
    raw = raw.strip().strip("'\"")
    if raw in field_lookup:
        return raw
    lower_map = {k.lower(): k for k in field_lookup}
    if raw.lower() in lower_map:
        return lower_map[raw.lower()]
    # Fuzzy: check if any field name contains the raw text or vice versa
    for k in field_lookup:
        if raw.lower() in k.lower() or k.lower() in raw.lower():
            return k
    return None


def _parse_show_when(
    text: str,
    field_lookup: dict[str, Any],
    current_field_name: str | None = None,
    ordered_fields: list[str] | None = None,
) -> tuple[str, str] | None:
    """Parse natural-language showWhen/hideWhen text → (trigger_field_name, trigger_answer).

    Handles these SRS patterns:
    1. "If above selected is Volunteer" / "if above is yes" / "if above answer is yes"
    2. "If X selected in previous question" / "if option 2 is selected in the previous question"
    3. "If yes given in - FieldName" / "If no is selected in 'FieldName'"
    4. "FieldName is Value" / "If Field = Value"
    5. "If previous question was answered Yes"
    6. "If 'death of child' is selected in previous question"

    Args:
        text: The showWhen/hideWhen text from SRS
        field_lookup: All fields in the form {name: SRSFormField}
        current_field_name: Name of the field that has this condition
        ordered_fields: Fields in display order for "above"/"previous" resolution
    """
    text = text.strip().rstrip(".")
    if not text:
        return None

    text_lower = text.lower()

    # --- Pattern 1: "above" references (resolve to previous field in display order) ---
    above_patterns = [
        re.compile(r"(?:if|when)\s+above\s+(?:answer\s+)?(?:is\s+)?(?:selected\s+(?:as\s+)?)?['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
        re.compile(r"(?:if|when)\s+above\s+(?:is\s+)?['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
    ]
    if "above" in text_lower and ordered_fields and current_field_name:
        try:
            idx = ordered_fields.index(current_field_name)
            if idx > 0:
                prev_field = ordered_fields[idx - 1]
                for pat in above_patterns:
                    m = pat.match(text)
                    if m:
                        answer = m.group(1).strip().strip("'\"")
                        return prev_field, answer
        except ValueError:
            pass

    # --- Pattern 2: "previous question" references ---
    prev_q_patterns = [
        # "if X is selected in the previous question"
        re.compile(r"(?:if|show only if|when)\s+['\"]?(.+?)['\"]?\s+(?:is\s+)?selected\s+in\s+(?:the\s+)?previous\s+question", re.IGNORECASE),
        # "If previous question was answered Yes"
        re.compile(r"(?:if|when)\s+previous\s+question\s+(?:was\s+)?(?:answered\s+)?['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
        # "if 'death of child' is selected in previous question"
        re.compile(r"(?:if|when)\s+['\"](.+?)['\"]?\s+is\s+selected\s+in\s+(?:the\s+)?previous\s+question", re.IGNORECASE),
    ]
    if "previous question" in text_lower and ordered_fields and current_field_name:
        try:
            idx = ordered_fields.index(current_field_name)
            if idx > 0:
                prev_field = ordered_fields[idx - 1]
                for pat in prev_q_patterns:
                    m = pat.match(text)
                    if m:
                        answer = m.group(1).strip().strip("'\"")
                        # "option 2" / "option 3" → try to resolve to actual answer
                        if answer.lower().startswith("option "):
                            # Try numeric option index
                            try:
                                opt_idx = int(answer.split()[-1]) - 1
                                prev_f = field_lookup.get(prev_field)
                                if prev_f and prev_f.options and opt_idx < len(prev_f.options):
                                    answer = prev_f.options[opt_idx]
                            except (ValueError, IndexError):
                                pass
                        return prev_field, answer
        except ValueError:
            pass

    # --- Pattern 3: "yes/no given in - FieldName" / "yes/no selected in 'FieldName'" ---
    given_in_patterns = [
        # "If yes given in - Are you currently doing something..."
        # Also handles typo "give in" instead of "given in"
        re.compile(r"(?:if|when)\s+(yes|no)\s+(?:give[n]?|selected|answered)\s+(?:in|for)\s*[-–]?\s*['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
        # "If no is selected in 'does this case need...'"
        re.compile(r"(?:if|when)\s+(yes|no)\s+is\s+selected\s+in\s+['\"](.+?)['\"]", re.IGNORECASE),
        # "If yes is selected in 'FieldName'"
        re.compile(r"(?:if|when)\s+['\"]?(yes|no)['\"]?\s+(?:is\s+)?selected\s+in\s+['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
    ]
    for pat in given_in_patterns:
        m = pat.match(text)
        if m:
            answer = m.group(1).strip()
            raw_field = m.group(2).strip().strip("'\"")
            resolved = _resolve_field_name(raw_field, field_lookup)
            if resolved:
                return resolved, answer.capitalize()

    # --- Pattern 4: "FieldName is Value" / "If Field = Value" ---
    direct_patterns = [
        re.compile(r"(?:if|when)\s+(.+?)\s+(?:is|=|==)\s+['\"]?(.+?)['\"]?\s*$", re.IGNORECASE),
        re.compile(r"^(.+?)\s*(?:=|==)\s*(.+)$", re.IGNORECASE),
        # "Status of Hb check (first trimester) is Done - value known"
        re.compile(r"(.+?)\s+is\s+(.+)", re.IGNORECASE),
    ]
    for pat in direct_patterns:
        m = pat.match(text)
        if m:
            raw_field = m.group(1).strip().strip("'\"")
            raw_answer = m.group(2).strip().strip("'\"")
            resolved = _resolve_field_name(raw_field, field_lookup)
            if resolved:
                return resolved, raw_answer

    # --- Pattern 5: "If X is not selected" / "If currently pregnant is not selected" ---
    not_selected = re.match(
        r"(?:if|when)\s+['\"]?(.+?)['\"]?\s+is\s+not\s+selected",
        text, re.IGNORECASE,
    )
    if not_selected:
        raw_answer = not_selected.group(1).strip().strip("'\"")
        # This is a negative condition — find which field has this as an option
        for fname, fobj in field_lookup.items():
            if hasattr(fobj, 'options') and fobj.options:
                for opt in fobj.options:
                    if raw_answer.lower() in opt.lower() or opt.lower() in raw_answer.lower():
                        return fname, raw_answer  # Will need special handling for negation

    # --- Pattern 6: "if answer is X - FieldName" / "if answer is yes for FieldName" ---
    answer_is_patterns = [
        re.compile(r"(?:if|when)\s+answer\s+is\s+['\"]?(.+?)['\"]?\s*[-–]\s*(.+)", re.IGNORECASE),
        re.compile(r"(?:if|when)\s+answer\s+is\s+['\"]?(yes|no)['\"]?\s+(?:for|in)\s+(.+)", re.IGNORECASE),
    ]
    for pat in answer_is_patterns:
        m = pat.match(text)
        if m:
            raw_answer = m.group(1).strip().strip("'\"")
            raw_field = m.group(2).strip().strip("'\"")
            resolved = _resolve_field_name(raw_field, field_lookup)
            if resolved:
                return resolved, raw_answer.capitalize()

    # --- Pattern 7: "If 'above question is yes" (broken quote in SRS) ---
    if text_lower.startswith("if 'above question") or text_lower.startswith("if above question"):
        if ordered_fields and current_field_name:
            try:
                idx = ordered_fields.index(current_field_name)
                if idx > 0:
                    prev_field = ordered_fields[idx - 1]
                    return prev_field, "Yes"
            except ValueError:
                pass

    # --- Pattern 8: "once this is 'yes'" (self-reference for hideWhen) ---
    # These use latestInPreviousEncounters scope in production
    once_this = re.match(r"once\s+this\s+is\s+['\"]?(yes|no)['\"]?", text, re.IGNORECASE)
    if once_this and current_field_name:
        answer = once_this.group(1).capitalize()
        # Return special marker — the field references itself with a different scope
        return current_field_name, f"__SELF_PREV__:{answer}"

    return None


def _scope_for_form_type(form_type: str) -> str:
    if form_type in ("ProgramEncounter", "ProgramEncounterCancellation", "Encounter", "IndividualEncounterCancellation"):
        return "encounter"
    if form_type in ("ProgramEnrolment", "ProgramExit"):
        return "enrolment"
    return "registration"


def _entity_var_for_form_type(form_type: str) -> str:
    if form_type in ("ProgramEncounter", "ProgramEncounterCancellation"):
        return "programEncounter"
    if form_type in ("ProgramEnrolment", "ProgramExit"):
        return "programEnrolment"
    if form_type in ("Encounter", "IndividualEncounterCancellation"):
        return "encounter"
    return "individual"


def _value_in_for_scope(scope: str) -> str:
    return {"encounter": "valueInEncounter", "enrolment": "valueInEnrolment"}.get(scope, "valueInRegistration")


def _date_field_for_form_type(form_type: str) -> str:
    if form_type in ("ProgramEnrolment",):
        return "enrolmentDateTime"
    return "encounterDateTime"


# ---------------------------------------------------------------------------
# Declarative rule builders (exact Avni format)
# ---------------------------------------------------------------------------

def _build_declarative_skip_rule(
    trigger_concept_name: str,
    trigger_concept_uuid: str,
    trigger_concept_data_type: str,
    answer_names: list[str],
    answer_uuids: list[str],
    scope: str,
    action: str = "showFormElement",
    operator: str = "containsAnswerConceptName",
) -> list[dict[str, Any]]:
    """Build a declarative rule JSON in exact Avni format."""
    if operator in ("defined", "notDefined"):
        rhs: dict[str, Any] = {}
    elif answer_names:
        rhs = {
            "type": "answerConcept",
            "answerConceptNames": answer_names,
            "answerConceptUuids": answer_uuids,
        }
    else:
        rhs = {"type": "value", "value": None}

    return [{
        "conditions": [{
            "compoundRule": {
                "conjunction": "and",
                "rules": [{
                    "lhs": {
                        "type": "concept",
                        "scope": scope,
                        "conceptName": trigger_concept_name,
                        "conceptUuid": trigger_concept_uuid,
                        "conceptDataType": trigger_concept_data_type,
                    },
                    "operator": operator,
                    "rhs": rhs,
                }],
            },
        }],
        "actions": [{"actionType": action}, {}],
    }]


def _build_declarative_visit_schedule(
    encounter_type_name: str,
    encounter_name: str,
    days_to_schedule: int,
    days_to_overdue: int,
    date_field: str = "encounterDateTime",
) -> list[dict[str, Any]]:
    """Build a visit schedule declarative rule in exact Avni format."""
    return [{
        "conditions": [{
            "compoundRule": {
                "rules": [{
                    "lhs": {"type": "lowestAddressLevel"},
                    "rhs": {},
                    "operator": "defined",
                }],
            },
        }],
        "actions": [{
            "actionType": "scheduleVisit",
            "details": {
                "encounterType": encounter_type_name,
                "encounterName": encounter_name,
                "dateField": date_field,
                "daysToSchedule": str(days_to_schedule),
                "daysToOverdue": str(days_to_overdue),
            },
        }, {}],
    }]


def _build_declarative_validation(
    concept_name: str,
    concept_uuid: str,
    operator: str,
    value: float,
    error_message: str,
    scope: str,
) -> dict[str, Any]:
    """Build a single validation declarative rule entry."""
    return {
        "conditions": [{
            "compoundRule": {
                "conjunction": "and",
                "rules": [{
                    "lhs": {
                        "type": "concept",
                        "scope": scope,
                        "conceptName": concept_name,
                        "conceptUuid": concept_uuid,
                        "conceptDataType": "Numeric",
                    },
                    "operator": operator,
                    "rhs": {"type": "value", "value": value},
                }],
            },
        }],
        "actions": [{
            "actionType": "formValidationError",
            "details": {"validationError": error_message},
        }, {}],
    }


# ---------------------------------------------------------------------------
# JS code generators (matching Avni's rules-config output exactly)
# ---------------------------------------------------------------------------

def _generate_skip_logic_js(
    trigger_concept_uuid: str,
    answer_uuids: list[str],
    form_type: str,
    operator: str = "containsAnswerConceptName",
) -> str:
    entity_var = _entity_var_for_form_type(form_type)
    scope = _scope_for_form_type(form_type)
    value_in = _value_in_for_scope(scope)

    # Build operator call
    if operator == "containsAnswerConceptName" and len(answer_uuids) == 1:
        op_call = f'.containsAnswerConceptName("{answer_uuids[0]}")'
    elif operator == "containsAnyAnswerConceptName":
        args = ",".join(f'"{u}"' for u in answer_uuids)
        op_call = f'.containsAnyAnswerConceptName({args})'
    elif operator in ("defined", "notDefined"):
        op_call = f'.{operator}'
    else:
        op_call = f'.containsAnswerConceptName("{answer_uuids[0] if answer_uuids else ""}")'

    return f"""'use strict';
({{params, imports}}) => {{
  const {entity_var} = params.entity;
  const moment = imports.moment;
  const formElement = params.formElement;
  const _ = imports.lodash;
  let visibility = true;
  let value = null;
  let answersToSkip = [];
  let validationErrors = [];

  const condition11 = new imports.rulesConfig.RuleCondition({{{entity_var}, formElement}}).when.{value_in}("{trigger_concept_uuid}"){op_call}.matches();

  visibility = condition11 ;

  return new imports.rulesConfig.FormElementStatus(formElement.uuid, visibility, value, answersToSkip, validationErrors);
}};"""


def _generate_visit_schedule_js(
    form_type: str,
    encounter_type_name: str,
    encounter_name: str,
    days_to_schedule: int,
    days_to_overdue: int,
) -> str:
    entity_var = _entity_var_for_form_type(form_type)
    date_field = _date_field_for_form_type(form_type)

    exit_guard = ""
    if form_type in ("ProgramEncounter", "ProgramEncounterCancellation"):
        exit_guard = f" && !{entity_var}.programEnrolment.programExitDateTime"
    elif form_type == "ProgramEnrolment":
        exit_guard = f" && !{entity_var}.programExitDateTime"

    return f""""use strict";
({{ params, imports }}) => {{
  const {entity_var} = params.entity;
  const moment = imports.moment;
  const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({{{entity_var}}});

  const condition11 = new imports.rulesConfig.RuleCondition({{{entity_var}}}).when.lowestAddressLevel.defined.matches();

  if(condition11{exit_guard}){{
    const earliestDate = moment({entity_var}.{date_field}).add({days_to_schedule}, 'days').toDate();
    const maxDate = moment({entity_var}.{date_field}).add({days_to_overdue}, 'days').toDate();
    scheduleBuilder.add({{name: "{encounter_name}", encounterType: "{encounter_type_name}", earliestDate, maxDate}});
  }}

  return scheduleBuilder.getAll();
}};"""


def _generate_validation_js(
    validations: list[tuple[str, str, str, float | None, float | None]],
    form_type: str,
) -> str:
    """Generate form-level validation rule JS from numeric range checks.

    Matches exact Avni production format: returns array of validation error objects
    using ``imports.common.createValidationError()``.
    """
    entity_var = _entity_var_for_form_type(form_type)

    checks = []
    for name, concept_uuid, _, low, high in validations:
        if low is not None and high is not None:
            checks.append(
                f'  {{\n'
                f'    const val = {entity_var}.getObservationValue("{concept_uuid}");\n'
                f'    if (val !== undefined && val !== null && (val < {low} || val > {high})) {{\n'
                f'      validationResults.push(imports.common.createValidationError("{name} must be in range {low}-{high}"));\n'
                f'    }}\n'
                f'  }}'
            )
        elif low is not None:
            checks.append(
                f'  {{\n'
                f'    const val = {entity_var}.getObservationValue("{concept_uuid}");\n'
                f'    if (val !== undefined && val !== null && val < {low}) {{\n'
                f'      validationResults.push(imports.common.createValidationError("{name} must be >= {low}"));\n'
                f'    }}\n'
                f'  }}'
            )
        elif high is not None:
            checks.append(
                f'  {{\n'
                f'    const val = {entity_var}.getObservationValue("{concept_uuid}");\n'
                f'    if (val !== undefined && val !== null && val > {high}) {{\n'
                f'      validationResults.push(imports.common.createValidationError("{name} must be <= {high}"));\n'
                f'    }}\n'
                f'  }}'
            )

    if not checks:
        return ""

    return f""""use strict";
({{ params, imports }}) => {{
  const {entity_var} = params.entity;
  const moment = imports.moment;
  const validationResults = [];

{"".join(checks)}

  return validationResults;
}};"""


def _generate_date_validation_js(form_type: str) -> str:
    """Generate date-check validation JS matching Avni production format.

    Validates that encounter/cancel date is within the visit scheduling window:
    - encounterDateTime >= earliestVisitDateTime - 5 days
    - encounterDateTime < maxVisitDateTime (if set)

    For cancellation forms, uses cancelDateTime instead.
    """
    entity_var = _entity_var_for_form_type(form_type)
    is_cancel = "Cancel" in form_type or "Cancellation" in form_type

    date_field = "cancelDateTime" if is_cancel else "encounterDateTime"

    exit_guard = ""
    if form_type in ("ProgramEncounterCancellation",):
        exit_guard = " && !programEncounter.programEnrolment.programExitDateTime"

    too_early_msg = "This visit cannot be cancelled sooner" if is_cancel else "This visit cannot be completed sooner"
    overdue_msg = "Overdue forms cannot be filled, please cancel this form so that next due form can be scheduled"

    lines = [
        f"'use strict';",
        f"({{params, imports}}) => {{",
        f"  const {entity_var} = params.entity;",
        f"  const moment = imports.moment;",
        f"  const validationResults = [];",
        f"",
        f"  let dateToCheck = moment({entity_var}.{date_field}).format('YYYY-MM-DD');",
        f"  let earliestVisitDateTime = moment({entity_var}.earliestVisitDateTime).subtract(5,'days').format('YYYY-MM-DD');",
        f"  let maxVisitDateTime = {entity_var}.maxVisitDateTime ? moment({entity_var}.maxVisitDateTime).format('YYYY-MM-DD') : null;",
        f"",
    ]

    if exit_guard:
        lines.append(f"  if ({exit_guard.strip(' && !')})")
        lines.append(f"    return validationResults;")
        lines.append(f"")
        lines.append(f"  if ( !( dateToCheck >= earliestVisitDateTime ) ) {{")
    else:
        lines.append(f"  if ( !( dateToCheck >= earliestVisitDateTime ) ) {{")

    lines.extend([
        f'    validationResults.push(imports.common.createValidationError("{too_early_msg}"));',
        f"  }};",
        f"",
    ])

    if not is_cancel:
        lines.extend([
            f"  if ( maxVisitDateTime && dateToCheck >= maxVisitDateTime ) {{",
            f'    validationResults.push(imports.common.createValidationError("{overdue_msg}"));',
            f"  }};",
            f"",
        ])

    lines.extend([
        f"  return validationResults;",
        f"}};",
    ])

    return "\n".join(lines)


def _generate_cancel_reschedule_js(
    form_type: str,
    encounter_type_name: str,
    days_to_schedule: int,
    days_to_overdue: int,
) -> str:
    """Generate cancel-reschedule visit schedule JS matching Avni production format.

    When a visit is cancelled, reschedule the same encounter type after a delay.
    Checks program exit status before rescheduling.
    """
    entity_var = _entity_var_for_form_type(form_type)

    exit_check = ""
    if "Program" in form_type:
        exit_check = f" && !{entity_var}.programEnrolment.programExitDateTime"

    return f""""use strict";
({{ params, imports }}) => {{
  const {entity_var} = params.entity;
  const moment = imports.moment;
  const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({{{entity_var}}});

  const earliestDate = moment({entity_var}.cancelDateTime).add({days_to_schedule}, 'days').toDate();
  const maxDate = moment({entity_var}.cancelDateTime).add({days_to_overdue}, 'days').toDate();

  if ({entity_var}.cancelDateTime{exit_check}) {{
    scheduleBuilder.add({{name: "{encounter_type_name}", encounterType: "{encounter_type_name}", earliestDate, maxDate}});
  }}

  return scheduleBuilder.getAll();
}};"""


# Visit intervals: (days_to_schedule, days_to_overdue, visit_name_override)
_ENCOUNTER_SCHEDULE: dict[str, tuple[int, int, str | None]] = {
    "ANC": (28, 35, "ANC"),
    "PNC": (0, 2, "PNC"),
    "Home Visit": (28, 35, None),
    "Anthropometry": (28, 35, None),
    "Follow up": (14, 21, None),
    "Follow-up": (14, 21, None),
    "Referral Follow up": (14, 21, None),
    "Referral Follow-up": (14, 21, None),
    "Assessment": (30, 37, None),
    "Milestone": (90, 97, None),
}


class RuleInjector:
    """Injects auto-generated rules (declarative JSON + JS) into bundle forms.

    Generates all rule types that can be reliably auto-generated from SRS metadata:
    - Skip logic (showWhen/hideWhen → declarative + JS)
    - Visit schedules (encounter → next visit, enrolment → first visit)
    - Cancel-reschedule visit schedules (cancellation → reschedule same type)
    - Numeric validation (lowAbsolute/highAbsolute range checks)
    - Date-check validation (encounter/cancel date within scheduling window)
    - FEG-level declarative rules (group show/hide conditions)
    """

    def __init__(
        self,
        concepts: ConceptManager,
        registry: UUIDRegistry,
        all_form_defs: list[SRSFormDefinition] | None = None,
        visit_schedules: list[dict[str, Any]] | None = None,
    ):
        self._concepts = concepts
        self._registry = registry
        self._all_form_defs = all_form_defs or []
        self._visit_schedules = visit_schedules or []
        self._stats = {
            "skip_logic": 0,
            "visit_schedule": 0,
            "cancel_reschedule": 0,
            "validation": 0,
            "date_validation": 0,
            "feg_rule": 0,
        }

    def _find_first_encounter_type_for_program(self, program_name: str) -> str | None:
        """Find the first scheduled encounter type for a program from other forms.

        Searches ProgramEncounter forms first, then falls back to general Encounter
        forms whose names suggest they belong to the program (e.g. "ANC" for "Pregnancy",
        "Child Home Visit" for "Child").
        """
        # Direct match: ProgramEncounter linked to this program
        for f in self._all_form_defs:
            if f.formType == "ProgramEncounter" and f.programName == program_name and f.encounterTypeName:
                return f.encounterTypeName

        # Heuristic: find the first general Encounter form that looks like it belongs
        # to this program based on common naming patterns
        program_lower = program_name.lower()
        # Map program names to likely first encounter types
        program_encounter_hints: dict[str, list[str]] = {
            "pregnancy": ["anc", "ante", "maternal"],
            "child": ["child home visit", "child", "anthropomet", "growth"],
            "nutrition": ["nutrition", "anthropomet", "growth"],
            "referral": ["referral follow"],
        }

        # Find matching hints
        for keyword, hints in program_encounter_hints.items():
            if keyword in program_lower:
                for f in self._all_form_defs:
                    if f.formType == "Encounter" and f.encounterTypeName:
                        et_lower = f.encounterTypeName.lower()
                        for hint in hints:
                            if hint in et_lower and "referral" not in et_lower and "exit" not in et_lower and "cancel" not in et_lower:
                                return f.encounterTypeName

        # Last resort: take the first Encounter form that isn't a referral/exit/cancel
        for f in self._all_form_defs:
            if f.formType == "Encounter" and f.encounterTypeName:
                et_lower = f.encounterTypeName.lower()
                if "referral" not in et_lower and "exit" not in et_lower and "cancel" not in et_lower:
                    return f.encounterTypeName

        return None

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # -- Skip logic from showWhen / hideWhen keyValues ---

    def inject_element_rule(
        self,
        element: dict[str, Any],
        field: SRSFormField,
        form_def: SRSFormDefinition,
        all_fields: dict[str, SRSFormField],
        ordered_field_names: list[str] | None = None,
    ) -> None:
        """Parse showWhen/hideWhen and inject both declarativeRule + rule JS.

        Uses the enhanced NL parser that handles patterns like:
        - "If above selected is Volunteer"
        - "If yes given in - FieldName"
        - "If X selected in previous question"
        - "FieldName is Value"
        """
        kvs = field.keyValues or []
        show_when_text = next((kv["value"] for kv in kvs if kv.get("key") == "showWhen"), None)
        hide_when_text = next((kv["value"] for kv in kvs if kv.get("key") == "hideWhen"), None)

        is_hide = hide_when_text is not None
        condition_text = show_when_text or hide_when_text
        if not condition_text:
            return

        parsed = _parse_show_when(
            condition_text, all_fields,
            current_field_name=field.name,
            ordered_fields=ordered_field_names,
        )
        if not parsed:
            logger.debug(
                "Could not parse skip condition for '%s' in form '%s': %s",
                field.name, form_def.name, condition_text,
            )
            return

        trigger_name, trigger_answer = parsed
        trigger_field = all_fields.get(trigger_name)
        if not trigger_field:
            return

        # For non-Coded fields, we can still generate rules if the answer is Yes/No
        if trigger_field.dataType != "Coded":
            # Skip non-coded triggers unless they could reasonably be treated as coded
            return

        trigger_concept = self._concepts._concepts.get(f"concept:{trigger_name.lower()}")
        if not trigger_concept:
            return

        # Handle self-referencing rules ("once this is 'yes'")
        # These use latestInPreviousEncounters scope in production
        use_prev_encounter_scope = False
        if trigger_answer.startswith("__SELF_PREV__:"):
            trigger_answer = trigger_answer.split(":", 1)[1]
            use_prev_encounter_scope = True

        # Fuzzy match the answer against available options
        answer_uuid = ""
        matched_answer_name = trigger_answer
        for ans in trigger_concept.get("answers", []):
            if ans["name"].lower() == trigger_answer.lower():
                answer_uuid = ans["uuid"]
                matched_answer_name = ans["name"]
                break
        # Fuzzy fallback: partial match
        if not answer_uuid:
            for ans in trigger_concept.get("answers", []):
                if trigger_answer.lower() in ans["name"].lower() or ans["name"].lower() in trigger_answer.lower():
                    answer_uuid = ans["uuid"]
                    matched_answer_name = ans["name"]
                    break
        if not answer_uuid:
            return

        scope = _scope_for_form_type(form_def.formType)
        if use_prev_encounter_scope:
            scope = "latestInPreviousEncounters"
        action = "hideFormElement" if is_hide else "showFormElement"

        # Declarative rule JSON
        element["declarativeRule"] = _build_declarative_skip_rule(
            trigger_concept["name"], trigger_concept["uuid"], trigger_concept["dataType"],
            [matched_answer_name], [answer_uuid],
            scope, action,
        )

        # Generated JS (for self-ref rules, use the declarative-only approach since
        # the JS pattern for latestInPreviousEncounters is more complex)
        if not use_prev_encounter_scope:
            element["rule"] = _generate_skip_logic_js(
                trigger_concept["uuid"], [answer_uuid], form_def.formType,
            )
        self._stats["skip_logic"] += 1

    # -- Visit schedule rules ---

    def generate_visit_schedule(self, form_def: SRSFormDefinition) -> tuple[str, list | None]:
        """Generate visit schedule (JS + declarative JSON) for encounter forms.

        For cancellation forms, generates a cancel-reschedule rule instead.
        Returns (js_rule, declarative_rule_or_none).
        """
        if form_def.formType not in (
            "ProgramEncounter", "ProgramEncounterCancellation",
            "IndividualEncounterCancellation", "ProgramEnrolment", "Encounter",
        ):
            return "", None

        # For enrolment forms, look up the first encounter type in the program
        if form_def.formType == "ProgramEnrolment":
            et_name = form_def.encounterTypeName
            if not et_name and form_def.programName:
                et_name = self._find_first_encounter_type_for_program(form_def.programName)
            if not et_name:
                return "", None
        else:
            if not form_def.encounterTypeName:
                return "", None
            et_name = form_def.encounterTypeName
        date_field = _date_field_for_form_type(form_def.formType)

        # Match against SRS visit schedules first, then fall back to heuristics
        days_to_schedule = 28
        days_to_overdue = 35
        visit_name = et_name
        matched_from_srs = False

        # Check parsed visit scheduling sheet data
        if self._visit_schedules:
            et_lower = et_name.lower()
            for vs in self._visit_schedules:
                trigger = (vs.get("trigger") or "").lower()
                sched_enc = (vs.get("schedule_encounter") or "").lower()
                # Match if the encounter type appears in trigger or schedule_encounter
                if et_lower in trigger or et_lower in sched_enc or trigger in et_lower or sched_enc in et_lower:
                    if "due_days" in vs:
                        days_to_schedule = vs["due_days"]
                    if "overdue_days" in vs:
                        days_to_overdue = vs["overdue_days"]
                    if vs.get("schedule_encounter"):
                        visit_name = vs["schedule_encounter"]
                    matched_from_srs = True
                    logger.info(
                        "Visit schedule from SRS: %s → due=%d, overdue=%d",
                        et_name, days_to_schedule, days_to_overdue,
                    )
                    break

        # Fall back to heuristic patterns if no SRS match
        if not matched_from_srs:
            for pattern, (sched, overdue, name_override) in _ENCOUNTER_SCHEDULE.items():
                if pattern.lower() in et_name.lower():
                    days_to_schedule = sched
                    days_to_overdue = overdue
                    if name_override:
                        visit_name = name_override
                    break

        # --- Cancellation forms: generate cancel-reschedule ---
        if form_def.formType in ("ProgramEncounterCancellation", "IndividualEncounterCancellation"):
            js_rule = _generate_cancel_reschedule_js(
                form_def.formType, et_name,
                days_to_schedule, days_to_overdue,
            )
            # Cancellation visit schedules use the same declarative format
            decl_rule = _build_declarative_visit_schedule(
                et_name, et_name,
                days_to_schedule, days_to_overdue,
                "cancelDateTime",
            )
            if js_rule:
                self._stats["cancel_reschedule"] += 1
            return js_rule, decl_rule

        # --- Enrolment forms: schedule first encounter ---
        if form_def.formType == "ProgramEnrolment":
            days_to_schedule = 0
            days_to_overdue = 7
            encounter_name = f"{visit_name} 1"
        else:
            encounter_name = visit_name

        js_rule = _generate_visit_schedule_js(
            form_def.formType, et_name, encounter_name,
            days_to_schedule, days_to_overdue,
        )
        decl_rule = _build_declarative_visit_schedule(
            et_name, encounter_name,
            days_to_schedule, days_to_overdue,
            date_field,
        )

        if js_rule:
            self._stats["visit_schedule"] += 1

        return js_rule, decl_rule

    # -- Numeric validation rules ---

    def generate_validation_rule(self, form_def: SRSFormDefinition) -> tuple[str, list | None]:
        """Generate validation rule (JS + declarative JSON) for forms.

        Combines two types of validation:
        1. Numeric range checks (from lowAbsolute/highAbsolute in SRS fields)
        2. Date-check validation (for encounter/cancellation forms: check dates
           against earliest/max visit scheduling window)

        Returns (js_rule, declarative_rule_or_none).
        """
        scope = _scope_for_form_type(form_def.formType)
        validations: list[tuple[str, str, str, float | None, float | None]] = []
        decl_rules: list[dict[str, Any]] = []

        for group in form_def.groups:
            for field in group.fields:
                if field.dataType != "Numeric":
                    continue
                if field.lowAbsolute is None and field.highAbsolute is None:
                    continue

                concept = self._concepts._concepts.get(f"concept:{field.name.lower()}")
                if not concept:
                    continue

                validations.append((
                    field.name, concept["uuid"], concept["dataType"],
                    field.lowAbsolute, field.highAbsolute,
                ))

                # Declarative rules for each bound
                if field.lowAbsolute is not None:
                    decl_rules.append(_build_declarative_validation(
                        field.name, concept["uuid"], "lessThan", field.lowAbsolute,
                        f"{field.name} must be >= {field.lowAbsolute}",
                        scope,
                    ))
                if field.highAbsolute is not None:
                    decl_rules.append(_build_declarative_validation(
                        field.name, concept["uuid"], "greaterThan", field.highAbsolute,
                        f"{field.name} must be <= {field.highAbsolute}",
                        scope,
                    ))

        # Date-check validation for encounter/cancellation forms
        date_check_types = (
            "ProgramEncounter", "Encounter",
            "ProgramEncounterCancellation", "IndividualEncounterCancellation",
        )
        has_date_validation = form_def.formType in date_check_types

        if validations and has_date_validation:
            # Combine numeric + date validation into one JS rule
            numeric_js = _generate_validation_js(validations, form_def.formType)
            date_js = _generate_date_validation_js(form_def.formType)
            # Merge: take the numeric JS and insert date checks before the return
            # Simpler approach: use date validation as the base, numeric is secondary
            js_rule = date_js  # Date validation is more important
            self._stats["validation"] += 1
            self._stats["date_validation"] += 1
            return js_rule, decl_rules if decl_rules else None
        elif validations:
            js_rule = _generate_validation_js(validations, form_def.formType)
            self._stats["validation"] += 1
            return js_rule, decl_rules if decl_rules else None
        elif has_date_validation:
            js_rule = _generate_date_validation_js(form_def.formType)
            self._stats["date_validation"] += 1
            return js_rule, None

        return "", None


# ---------------------------------------------------------------------------
# Decision rule JS generator — from SRS Decisions sheet
# ---------------------------------------------------------------------------

def _generate_decision_rule_js(
    decisions: list[dict[str, Any]],
    form_type: str,
    concepts: ConceptManager,
) -> str:
    """Generate a form-level decisionRule JS from SRS Decisions sheet entries.

    Handles:
    - Conditional decisions (When condition → set field = value)
    - ALWAYS decisions (auto-stamp, copy, formula)
    - {FieldName} references resolved to getObservationValue calls
    - {CURRENT_DATE}, {CURRENT_USER} special tokens
    - Complications pattern: multiple rows with same Set Field build an array
    """
    if not decisions:
        return ""

    entity_var = _entity_var_for_form_type(form_type)
    scope = _scope_for_form_type(form_type)
    scope_var = f"{scope}Decisions"

    # Group decisions by Set Field to detect complications (multi-value) pattern
    by_field: dict[str, list[dict[str, Any]]] = {}
    for d in decisions:
        by_field.setdefault(d["setField"], []).append(d)

    blocks: list[str] = []
    for set_field, field_decisions in by_field.items():
        is_multi = len(field_decisions) > 1 and all(
            d.get("when", "ALWAYS").upper() != "ALWAYS" for d in field_decisions
        )

        if is_multi:
            # Complications pattern: build array of values from conditions
            blocks.append(f'  // {set_field} (multi-value)')
            blocks.append(f'  const _{_safe_var(set_field)}Values = [];')
            for d in field_decisions:
                condition_js = _condition_to_js(d["when"], entity_var, concepts)
                value_js = _value_to_js(d["toValue"], entity_var, concepts)
                blocks.append(f'  if ({condition_js}) {{ _{_safe_var(set_field)}Values.push({value_js}); }}')
            blocks.append(f'  if (_{_safe_var(set_field)}Values.length > 0) {{')
            blocks.append(f'    {scope_var}.push({{name: "{set_field}", value: _{_safe_var(set_field)}Values}});')
            blocks.append(f'  }}')
        else:
            for d in field_decisions:
                value_js = _value_to_js(d["toValue"], entity_var, concepts)
                if d.get("when", "ALWAYS").upper() == "ALWAYS":
                    blocks.append(f'  // {set_field} (always)')
                    blocks.append(f'  {scope_var}.push({{name: "{set_field}", value: {value_js}}});')
                else:
                    condition_js = _condition_to_js(d["when"], entity_var, concepts)
                    blocks.append(f'  // {set_field}')
                    blocks.append(f'  if ({condition_js}) {{')
                    blocks.append(f'    {scope_var}.push({{name: "{set_field}", value: {value_js}}});')
                    blocks.append(f'  }}')

    return f""""use strict";
({{params, imports}}) => {{
  const {entity_var} = params.entity;
  const decisions = params.decisions;
  const moment = imports.moment;
  const _ = imports.lodash;
  const encounterDecisions = [];
  const enrolmentDecisions = [];
  const registrationDecisions = [];

{chr(10).join(blocks)}

  decisions.encounterDecisions.push(...encounterDecisions);
  decisions.enrolmentDecisions.push(...enrolmentDecisions);
  decisions.registrationDecisions.push(...registrationDecisions);
  return decisions;
}};"""


def _safe_var(name: str) -> str:
    """Convert a concept name to a safe JS variable name."""
    return re.sub(r'[^a-zA-Z0-9]', '_', name)


def _condition_to_js(when: str, entity_var: str, concepts: ConceptManager) -> str:
    """Convert a structured condition string to JS boolean expression."""
    if when.upper() == "ALWAYS":
        return "true"

    # Handle AND / OR compounds
    if " AND " in when:
        parts = when.split(" AND ")
        return " && ".join(f"({_condition_to_js(p.strip(), entity_var, concepts)})" for p in parts)
    if " OR " in when:
        parts = when.split(" OR ")
        return " || ".join(f"({_condition_to_js(p.strip(), entity_var, concepts)})" for p in parts)

    # Single condition patterns
    for pat, op_js in [
        (re.compile(r"^(.+?)\s*>=\s*(.+)$"), ">="),
        (re.compile(r"^(.+?)\s*<=\s*(.+)$"), "<="),
        (re.compile(r"^(.+?)\s*!=\s*(.+)$"), "!=="),
        (re.compile(r"^(.+?)\s*>\s*(.+)$"), ">"),
        (re.compile(r"^(.+?)\s*<\s*(.+)$"), "<"),
        (re.compile(r"^(.+?)\s*=\s*(.+)$"), "==="),
    ]:
        m = pat.match(when)
        if m:
            field = m.group(1).strip()
            val = m.group(2).strip()
            concept = concepts._concepts.get(f"concept:{field.lower()}")
            concept_uuid = concept["uuid"] if concept else field
            # Numeric comparison vs string comparison
            try:
                float(val)
                return f'{entity_var}.getObservationValue("{concept_uuid}") {op_js} {val}'
            except ValueError:
                # Coded field — check answer name
                if concept and concept.get("dataType") == "Coded":
                    return f'new imports.rulesConfig.RuleCondition({{{entity_var}}}).when.valueInEncounter("{concept_uuid}").containsAnswerConceptName("{val}").matches()'
                return f'{entity_var}.getObservationReadableValue("{concept_uuid}") {op_js} "{val}"'

    # IS EMPTY / IS NOT EMPTY
    m = re.match(r"^(.+?)\s+IS\s+NOT\s+EMPTY$", when, re.IGNORECASE)
    if m:
        field = m.group(1).strip()
        concept = concepts._concepts.get(f"concept:{field.lower()}")
        concept_uuid = concept["uuid"] if concept else field
        return f'{entity_var}.getObservationValue("{concept_uuid}") !== undefined && {entity_var}.getObservationValue("{concept_uuid}") !== null'
    m = re.match(r"^(.+?)\s+IS\s+EMPTY$", when, re.IGNORECASE)
    if m:
        field = m.group(1).strip()
        concept = concepts._concepts.get(f"concept:{field.lower()}")
        concept_uuid = concept["uuid"] if concept else field
        return f'({entity_var}.getObservationValue("{concept_uuid}") === undefined || {entity_var}.getObservationValue("{concept_uuid}") === null)'

    return "true /* unparsed condition */"


def _value_to_js(to_value: str, entity_var: str, concepts: ConceptManager) -> str:
    """Convert a To Value expression to JS.

    Handles:
    - Plain strings: "High" → "High"
    - {FieldName} references: {Weight} → entity.getObservationValue("uuid")
    - {CURRENT_DATE} → moment().format("YYYY-MM-DD")
    - {CURRENT_USER} → params.user.name
    - Arithmetic: {Weight} / ({Height} / 100) ^ 2
    """
    if not to_value:
        return '""'

    if to_value == "{CURRENT_DATE}":
        return 'imports.moment().format("YYYY-MM-DD HH:mm:ss")'
    if to_value == "{CURRENT_USER}":
        return "params.user.name"

    # Check if it contains {field} references
    refs = re.findall(r"\{([^}]+)\}", to_value)
    if refs:
        # It's a formula or template with field references
        js_expr = to_value
        for ref in refs:
            concept = concepts._concepts.get(f"concept:{ref.lower()}")
            concept_uuid = concept["uuid"] if concept else ref
            js_expr = js_expr.replace(f"{{{ref}}}", f'{entity_var}.getObservationValue("{concept_uuid}")')
        # Replace ^ with Math.pow
        js_expr = re.sub(r'(\S+)\s*\^\s*(\S+)', r'Math.pow(\1, \2)', js_expr)
        return js_expr

    # Plain string value
    return f'"{to_value}"'


# ---------------------------------------------------------------------------
# Eligibility rule JS generator — from SRS Eligibility sheet
# ---------------------------------------------------------------------------

def _generate_eligibility_rule_js(condition: str) -> str:
    """Generate a program eligibility check rule JS from a structured condition.

    The condition uses the same format as Show When, plus Age/Gender keywords.
    Returns JS string for program.enrolmentEligibilityCheckRule.
    """
    if not condition:
        return ""

    js_parts: list[str] = []

    # Handle AND / OR
    if " AND " in condition:
        parts = condition.split(" AND ")
        js_parts = [_eligibility_atom_to_js(p.strip()) for p in parts]
        body = " && ".join(js_parts)
    elif " OR " in condition:
        parts = condition.split(" OR ")
        js_parts = [_eligibility_atom_to_js(p.strip()) for p in parts]
        body = " || ".join(js_parts)
    else:
        body = _eligibility_atom_to_js(condition)

    return f"""'use strict';
({{params, imports}}) => {{
  const individual = params.entity;
  return {body};
}};"""


def _eligibility_atom_to_js(atom: str) -> str:
    """Convert a single eligibility condition atom to JS expression."""
    atom = atom.strip()

    # Gender = Female / Gender = Male
    m = re.match(r"Gender\s*=\s*(\w+)", atom, re.IGNORECASE)
    if m:
        gender = m.group(1).capitalize()
        if gender == "Female":
            return "individual.isFemale()"
        elif gender == "Male":
            return "individual.isMale()"
        return f'individual.gender.name === "{gender}"'

    # Age > N / Age >= N / Age < N / Age <= N
    m = re.match(r"Age\s*(>=|<=|>|<|=)\s*(\d+)", atom, re.IGNORECASE)
    if m:
        op = m.group(1)
        if op == "=":
            op = "==="
        val = m.group(2)
        return f"individual.getAgeInYears() {op} {val}"

    # Generic field = value
    m = re.match(r"(.+?)\s*=\s*(.+)", atom)
    if m:
        field = m.group(1).strip()
        val = m.group(2).strip()
        return f'individual.getObservationReadableValue("{field}") === "{val}"'

    return f"true /* unparsed: {atom} */"


# ---------------------------------------------------------------------------
# Report card + dashboard generator — from SRS Report Cards sheet
# ---------------------------------------------------------------------------

# Map card type names to standard report card type UUIDs (from avni-server seed data)
_STANDARD_CARD_TYPE_UUIDS = {
    "Total": "1fbcadf3-bf1a-439e-9e13-24adddfbf6c0",
    "RecentRegistrations": "88a7514c-48c0-4d5d-a421-d074e43bb36c",
    "RecentEnrolments": "a5efc04c-317a-4823-a203-e62603454a65",
    "RecentVisits": "77b5b3fa-de35-4f24-996b-2842492ea6e0",
    "ScheduledVisits": "27020b32-c21b-43a4-81bd-7b88ad3a6ef0",
    "OverdueVisits": "9f88bee5-2ab9-4ac4-ae19-d07e9715bdb5",
    # Legacy aliases for backward compatibility
    "TOTAL": "1fbcadf3-bf1a-439e-9e13-24adddfbf6c0",
    "RECENT_REGISTRATIONS": "88a7514c-48c0-4d5d-a421-d074e43bb36c",
    "RECENT_ENROLMENTS": "a5efc04c-317a-4823-a203-e62603454a65",
    "RECENT_VISITS": "77b5b3fa-de35-4f24-996b-2842492ea6e0",
    "SCHEDULED_VISITS": "27020b32-c21b-43a4-81bd-7b88ad3a6ef0",
    "OVERDUE_VISITS": "9f88bee5-2ab9-4ac4-ae19-d07e9715bdb5",
    "PendingApproval": "9e584c8d-b31d-4e5a-9161-baf4f369d02d",
    "Approved": "a65c064b-db32-408b-aceb-d15acfebca1e",
    "Rejected": "84d6c349-9fbb-41d3-85fe-1d34521a0d45",
    "Comments": "7726476c-fb91-4c28-8afc-9782714c1d8c",
    "Tasks": "PLACEHOLDER-TASKS",
    "CallTasks": "PLACEHOLDER-CALL-TASKS",
    "OpenSubjectTasks": "PLACEHOLDER-OPEN-SUBJECT-TASKS",
    "DueChecklist": "PLACEHOLDER-DUE-CHECKLIST",
}

_DURATION_TO_DAYS = {
    "1 day": 1, "1 week": 7, "1 month": 30,
    "2 weeks": 14, "3 months": 90, "6 months": 180,
    "1 year": 365,
}


def generate_report_cards(
    card_defs: list[dict[str, Any]],
    registry: UUIDRegistry,
    subject_types: list[dict[str, Any]],
    programs: list[dict[str, Any]],
    encounter_types: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Generate reportCard.json, reportDashboard.json, and groupDashboards.json from SRS.

    Returns (report_cards, report_dashboard, group_dashboards).
    """
    cards: list[dict[str, Any]] = []
    st_uuid_map = {st["name"]: st["uuid"] for st in subject_types}
    prog_uuid_map = {p["name"]: p["uuid"] for p in programs}
    et_uuid_map = {et["name"]: et["uuid"] for et in encounter_types}

    for card_def in card_defs:
        card_name = card_def["name"]
        card_type = card_def["cardType"]
        card_uuid = registry.stable_uuid(f"reportCard:{card_name}")

        card: dict[str, Any] = {
            "uuid": card_uuid,
            "name": card_name,
            "description": card_def.get("description", ""),
            "color": card_def.get("color", card_def.get("colour", "#666666")),
            "nested": card_def.get("nested", False),
            "count": card_def.get("count", 1),
            "voided": False,
            "query": None,
            "standardReportCardType": None,
            "iconFileS3Key": None,
            "standardReportCardInputSubjectTypes": [],
            "standardReportCardInputPrograms": [],
            "standardReportCardInputEncounterTypes": [],
        }

        # Build standardReportCardInput for standard cards
        if card_type != "Custom" and card_type in _STANDARD_CARD_TYPE_UUIDS:
            card["standardReportCardType"] = _STANDARD_CARD_TYPE_UUIDS[card_type]

            st_name = card_def.get("subjectType")
            if st_name and st_name in st_uuid_map:
                card["standardReportCardInputSubjectTypes"] = [st_uuid_map[st_name]]
            prog_name = card_def.get("program")
            if prog_name and prog_name in prog_uuid_map:
                card["standardReportCardInputPrograms"] = [prog_uuid_map[prog_name]]
            et_name = card_def.get("encounterType")
            if et_name and et_name in et_uuid_map:
                card["standardReportCardInputEncounterTypes"] = [et_uuid_map[et_name]]

            # Recent duration — must be a JSON string with string value
            dur = card_def.get("recentDuration", "")
            if dur and dur in _DURATION_TO_DAYS:
                import json as _json
                card["standardReportCardInputRecentDuration"] = _json.dumps(
                    {"value": str(_DURATION_TO_DAYS[dur]), "unit": "days"}
                )

        elif card_type == "Custom":
            filter_cond = card_def.get("filterCondition", "")
            st_name = card_def.get("subjectType", "Individual")
            prog_name = card_def.get("program")
            nested_count = card_def.get("nestedCount")
            if nested_count and nested_count > 1:
                card["nested"] = True
                card["count"] = nested_count
            card["query"] = _generate_report_card_query(
                filter_cond, st_name, prog_name, card_def.get("encounterType"),
            )

        cards.append(card)

    # Build dashboard with one section containing all cards
    dashboard_uuid = registry.stable_uuid("reportDashboard:main")
    section_uuid = registry.stable_uuid("reportDashboard:main:section1")

    card_mappings = []
    for i, card in enumerate(cards):
        card_mappings.append({
            "uuid": registry.stable_uuid(f"dashCardMapping:{card['name']}"),
            "displayOrder": float(i + 1),
            "dashboardSectionUUID": section_uuid,
            "reportCardUUID": card["uuid"],
            "voided": False,
        })

    dashboard = [{
        "uuid": dashboard_uuid,
        "name": "Dashboard",
        "description": "",
        "voided": False,
        "sections": [{
            "uuid": section_uuid,
            "name": "Overview",
            "description": "",
            "displayOrder": 1.0,
            "viewType": "Default",
            "voided": False,
            "dashboardSectionCardMappings": card_mappings,
        }],
    }]

    # Group dashboard: assign to Everyone group
    everyone_uuid = registry.stable_uuid("group:Everyone")
    group_dashboards = [{
        "uuid": registry.stable_uuid("groupDashboard:Everyone:main"),
        "voided": False,
        "dashboardUUID": dashboard_uuid,
        "groupUUID": everyone_uuid,
        "groupName": "Everyone",
        "dashboardName": "Dashboard",
        "dashboardDescription": "",
        "groupOneOfTheDefaultGroups": False,
        "primaryDashboard": True,
        "secondaryDashboard": False,
    }]

    return cards, dashboard, group_dashboards


def _generate_report_card_query(
    filter_condition: str,
    subject_type: str = "Individual",
    program: str | None = None,
    encounter_type: str | None = None,
) -> str:
    """Generate a Realm-based report card query JS from a filter condition."""
    filters = [f'subjectType.name = "{subject_type}"', 'voided = false']

    # Build subject query
    subject_query = " AND ".join(filters)

    # Build filter logic
    filter_js_parts: list[str] = []
    if filter_condition:
        for atom in re.split(r"\s+AND\s+", filter_condition, flags=re.IGNORECASE):
            atom = atom.strip()
            m = re.match(r"(.+?)\s*=\s*(.+)", atom)
            if m:
                field = m.group(1).strip()
                val = m.group(2).strip()
                filter_js_parts.append(
                    f'individual.getObservationReadableValue("{field}") === "{val}"'
                )
            m2 = re.match(r"(.+?)\s+IN\s*\((.+)\)", atom, re.IGNORECASE)
            if m2:
                field = m2.group(1).strip()
                vals = [v.strip() for v in m2.group(2).split(",")]
                val_arr = ", ".join(f'"{v}"' for v in vals)
                filter_js_parts.append(
                    f'[{val_arr}].includes(individual.getObservationReadableValue("{field}"))'
                )

    filter_body = " && ".join(filter_js_parts) if filter_js_parts else "true"

    if program:
        return f"""'use strict';
({{params, imports}}) => {{
  const _ = imports.lodash;
  return params.db.objects('Individual')
    .filtered('{subject_query}')
    .filter((individual) => {{
      const enrolment = _.last(individual.enrolments.filter(e => e.program.name === "{program}" && !e.programExitDateTime));
      return enrolment && ({filter_body});
    }});
}};"""

    return f"""'use strict';
({{params, imports}}) => {{
  const _ = imports.lodash;
  return params.db.objects('Individual')
    .filtered('{subject_query}')
    .filter((individual) => {filter_body});
}};"""


def _sanitize_filename(name: str) -> str:
    """Sanitize a string for use as a filename (no path separators or illegal chars)."""
    # Replace characters that are unsafe in filenames
    for ch in r'\/:"*?<>|':
        name = name.replace(ch, "_")
    return name.strip()


def _format_json(data: Any) -> str:
    """Serialize to JSON with float formatting for Avni-required keys."""
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    for key in FLOAT_KEYS:
        # Match "key": <integer> that is NOT already a float (no decimal point following).
        # The negative lookahead (?!\d*\.\d) prevents matching numbers already in float form.
        # We also need a word boundary / line context to avoid partial matches.
        pattern = rf'("{key}"\s*:\s*)(-?\d+)(\s*[,\n\r\}}])'
        def _replace_with_float(m: re.Match) -> str:
            prefix = m.group(1)
            number = m.group(2)
            suffix = m.group(3)
            return f"{prefix}{number}.0{suffix}"
        raw = re.sub(pattern, _replace_with_float, raw)
    return raw


def generate_address_level_types(
    srs: SRSData, registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate addressLevelTypes.json content."""
    if srs.addressLevelTypes:
        result = []
        for i, alt in enumerate(srs.addressLevelTypes):
            entry: dict[str, Any] = {
                "uuid": registry.stable_uuid(f"addressLevel:{alt['name']}"),
                "name": alt["name"],
                "level": float(alt.get("level", len(srs.addressLevelTypes) - i)),
                "voided": False,
            }
            if alt.get("parent"):
                entry["parent"] = {
                    "uuid": registry.stable_uuid(f"addressLevel:{alt['parent']}")
                }
            result.append(entry)
        return result

    # Default hierarchy
    state_uuid = registry.stable_uuid("addressLevel:State")
    district_uuid = registry.stable_uuid("addressLevel:District")
    block_uuid = registry.stable_uuid("addressLevel:Block")
    return [
        {"uuid": state_uuid, "name": "State", "level": 3.0, "voided": False},
        {
            "uuid": district_uuid,
            "name": "District",
            "level": 2.0,
            "parent": {"uuid": state_uuid},
            "voided": False,
        },
        {
            "uuid": block_uuid,
            "name": "Block",
            "level": 1.0,
            "parent": {"uuid": district_uuid},
            "voided": False,
        },
    ]


def generate_subject_types(
    srs: SRSData, registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate subjectTypes.json content."""
    # Valid Subject enum values from avni-server
    VALID_SUBJECT_ENUM = {"Person", "Individual", "Group", "Household", "User"}
    result = []
    for st in srs.subjectTypes:
        name = st.get("name", "Individual")
        raw_type = st.get("type", "Person")
        # Normalize: match case-insensitively to valid enum values
        st_type = "Person"  # default
        for valid in VALID_SUBJECT_ENUM:
            if raw_type.lower() == valid.lower():
                st_type = valid
                break
        result.append({
            "name": name,
            "uuid": registry.stable_uuid(f"subjectType:{name}"),
            "active": True,
            "type": st_type,
            "subjectSummaryRule": "",
            "programEligibilityCheckRule": "",
            "allowEmptyLocation": False,
            "allowMiddleName": st_type == "Person",
            "lastNameOptional": False,
            "allowProfilePicture": False,
            "uniqueName": False,
            "shouldSyncByLocation": True,
            "settings": {
                "displayRegistrationDetails": True,
                "displayPlannedEncounters": True,
            },
            "household": st_type == "Household",
            "group": st_type in ("Group", "Household"),
            "directlyAssignable": False,
            "voided": False,
        })
    return result


def generate_operational_subject_types(
    subject_types: list[dict[str, Any]], registry: UUIDRegistry,
) -> dict[str, Any]:
    """Generate operationalSubjectTypes.json content."""
    return {
        "operationalSubjectTypes": [
            {
                "uuid": registry.stable_uuid(f"opSubjectType:{st['name']}"),
                "subjectType": {"uuid": st["uuid"], "voided": False},
                "name": st["name"],
                "voided": False,
            }
            for st in subject_types
        ]
    }


PROGRAM_COLOURS = [
    "#E91E63", "#4CAF50", "#FF9800", "#2196F3", "#9C27B0",
    "#00BCD4", "#FF5722", "#607D8B", "#795548", "#3F51B5",
]


def generate_programs(
    srs: SRSData, registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate programs.json content."""
    result = []
    for i, prog in enumerate(srs.programs):
        name = prog.get("name", prog) if isinstance(prog, dict) else prog
        colour = (
            prog.get("colour", PROGRAM_COLOURS[i % len(PROGRAM_COLOURS)])
            if isinstance(prog, dict)
            else PROGRAM_COLOURS[i % len(PROGRAM_COLOURS)]
        )
        result.append({
            "name": name,
            "uuid": registry.stable_uuid(f"program:{name}"),
            "colour": colour,
            "programSubjectLabel": prog.get("programSubjectLabel", "") if isinstance(prog, dict) else "",
            "voided": False,
            "active": True,
            "enrolmentEligibilityCheckRule": "",
            "enrolmentSummaryRule": "",
            "enrolmentEligibilityCheckDeclarativeRule": None,
            "manualEligibilityCheckRequired": False,
            "showGrowthChart": False,
            "manualEnrolmentEligibilityCheckRule": "",
            "manualEnrolmentEligibilityCheckDeclarativeRule": None,
            "allowMultipleEnrolments": False,
        })
    return result


def generate_operational_programs(
    programs: list[dict[str, Any]], registry: UUIDRegistry,
) -> dict[str, Any]:
    """Generate operationalPrograms.json content."""
    return {
        "operationalPrograms": [
            {
                "uuid": registry.stable_uuid(f"opProgram:{p['name']}"),
                "program": {"uuid": p["uuid"], "voided": False},
                "name": p["name"],
                "programSubjectLabel": "",
                "voided": False,
            }
            for p in programs
        ]
    }


def generate_encounter_types(
    srs: SRSData, registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate encounterTypes.json content (avni-server EntityTypeContract)."""
    # Build set of general (non-program) encounter type names
    general_et_names: set[str] = set()
    if srs.generalEncounterTypes:
        general_et_names = {n.lower() for n in srs.generalEncounterTypes}

    return [
        {
            "name": name,
            "uuid": registry.stable_uuid(f"encounterType:{name}"),
            "encounterEligibilityCheckRule": "",
            "encounterEligibilityCheckDeclarativeRule": None,
            "programEncounter": name.lower() not in general_et_names,
            "active": True,
            "immutable": False,
            "voided": False,
        }
        for name in srs.encounterTypes
    ]


def generate_operational_encounter_types(
    encounter_types: list[dict[str, Any]], registry: UUIDRegistry,
) -> dict[str, Any]:
    """Generate operationalEncounterTypes.json content."""
    return {
        "operationalEncounterTypes": [
            {
                "uuid": registry.stable_uuid(f"opEncounterType:{et['name']}"),
                "encounterType": {"uuid": et["uuid"], "voided": False},
                "name": et["name"],
                "voided": False,
            }
            for et in encounter_types
        ]
    }


def generate_form_mappings(
    form_meta: list[dict[str, Any]],
    primary_subject_type_uuid: str,
    registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate formMappings.json content (avni-server FormMappingContract)."""
    mappings = []
    for fm in form_meta:
        st_uuid = fm.get("subjectTypeUUID", primary_subject_type_uuid)
        if "subjectTypeUUID" not in fm and fm["formType"] == "IndividualProfile":
            logger.warning(
                "Form '%s' (IndividualProfile) has no explicit subjectType — "
                "falling back to primary. This may map to the wrong subject type.",
                fm["formName"],
            )
        mapping: dict[str, Any] = {
            "uuid": registry.stable_uuid(
                f"formMapping:{fm['formName']}:{fm['formType']}"
            ),
            "formUUID": fm["formUUID"],
            "subjectTypeUUID": st_uuid,
            "formType": fm["formType"],
            "formName": fm["formName"],
            "enableApproval": False,
            "taskTypeUUID": None,
            "voided": False,
        }
        if fm.get("programUUID"):
            mapping["programUUID"] = fm["programUUID"]
        if fm.get("encounterTypeUUID"):
            mapping["encounterTypeUUID"] = fm["encounterTypeUUID"]
        mappings.append(mapping)
    return mappings


def generate_groups(
    group_names: list[str], registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate groups.json content."""
    result = []
    for name in group_names:
        is_everyone = name == "Everyone"
        group: dict[str, Any] = {
            "uuid": registry.stable_uuid(f"group:{name}"),
            "name": name,
            "voided": False,
            "hasAllPrivileges": is_everyone,
            "notEveryoneGroup": not is_everyone,
        }
        result.append(group)
    return result


PRIVILEGE_TYPES = [
    {"name": "ViewSubject", "level": "subjectType"},
    {"name": "RegisterSubject", "level": "subjectType"},
    {"name": "EditSubject", "level": "subjectType"},
    {"name": "VoidSubject", "level": "subjectType"},
    {"name": "EnrolSubject", "level": "program"},
    {"name": "ViewEnrolmentDetails", "level": "program"},
    {"name": "EditEnrolmentDetails", "level": "program"},
    {"name": "ExitEnrolment", "level": "program"},
    {"name": "ViewVisit", "level": "encounterType"},
    {"name": "ScheduleVisit", "level": "encounterType"},
    {"name": "PerformVisit", "level": "encounterType"},
    {"name": "EditVisit", "level": "encounterType"},
    {"name": "CancelVisit", "level": "encounterType"},
    {"name": "ViewChecklist", "level": "program"},
    {"name": "EditChecklist", "level": "program"},
]


def generate_group_privileges(
    group_names: list[str],
    subject_type_uuid: str,
    programs: list[dict[str, Any]],
    program_encounter_mappings: list[dict[str, Any]] | None,
    general_encounter_types: list[str] | None,
    registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate groupPrivilege.json content."""
    privileges = []
    pe_mappings = program_encounter_mappings or []
    ge_types = general_encounter_types or []

    for group_name in group_names:
        group_uuid = registry.stable_uuid(f"group:{group_name}")
        is_not_everyone = group_name != "Everyone"

        for priv in PRIVILEGE_TYPES:
            priv_uuid = registry.stable_uuid(f"privilege:{priv['name']}")

            if priv["level"] == "subjectType":
                privileges.append({
                    "uuid": _new_uuid(),
                    "groupUUID": group_uuid,
                    "privilegeUUID": priv_uuid,
                    "privilegeType": priv["name"],
                    "subjectTypeUUID": subject_type_uuid,
                    "programUUID": None,
                    "programEncounterTypeUUID": None,
                    "encounterTypeUUID": None,
                    "checklistDetailUUID": None,
                    "allow": True,
                    "notEveryoneGroup": is_not_everyone,
                    "voided": False,
                })

            elif priv["level"] == "program":
                for prog in programs:
                    privileges.append({
                        "uuid": _new_uuid(),
                        "groupUUID": group_uuid,
                        "privilegeUUID": priv_uuid,
                        "privilegeType": priv["name"],
                        "subjectTypeUUID": subject_type_uuid,
                        "programUUID": prog["uuid"],
                        "programEncounterTypeUUID": None,
                        "encounterTypeUUID": None,
                        "checklistDetailUUID": None,
                        "allow": True,
                        "notEveryoneGroup": is_not_everyone,
                        "voided": False,
                    })

            elif priv["level"] == "encounterType":
                # Program encounter types (use programEncounterTypeUUID
                # per GroupPrivilegeBundleContract)
                for mapping in pe_mappings:
                    prog_name = mapping.get("program", "")
                    for et_name in mapping.get("encounterTypes", []):
                        privileges.append({
                            "uuid": _new_uuid(),
                            "groupUUID": group_uuid,
                            "privilegeUUID": priv_uuid,
                            "privilegeType": priv["name"],
                            "subjectTypeUUID": subject_type_uuid,
                            "programUUID": registry.stable_uuid(
                                f"program:{prog_name}"
                            ),
                            "programEncounterTypeUUID": registry.stable_uuid(
                                f"encounterType:{et_name}"
                            ),
                            "encounterTypeUUID": None,
                            "checklistDetailUUID": None,
                            "allow": True,
                            "notEveryoneGroup": is_not_everyone,
                            "voided": False,
                        })

                # General encounter types (no program)
                for et_name in ge_types:
                    privileges.append({
                        "uuid": _new_uuid(),
                        "groupUUID": group_uuid,
                        "privilegeUUID": priv_uuid,
                        "privilegeType": priv["name"],
                        "subjectTypeUUID": subject_type_uuid,
                        "programUUID": None,
                        "programEncounterTypeUUID": None,
                        "encounterTypeUUID": registry.stable_uuid(
                            f"encounterType:{et_name}"
                        ),
                        "checklistDetailUUID": None,
                        "allow": True,
                        "notEveryoneGroup": is_not_everyone,
                        "voided": False,
                    })

    return privileges


def _infer_program_encounter_mappings(
    srs: SRSData, registry: UUIDRegistry,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Infer program-encounter mappings and general encounter types from form definitions."""
    if srs.programEncounterMappings is not None:
        return srs.programEncounterMappings, srs.generalEncounterTypes or []

    # Build mappings from form metadata
    program_encounters: dict[str, set[str]] = {}
    general_encounters: set[str] = set()

    for form_def in srs.forms:
        if form_def.formType in ("ProgramEncounter", "ProgramEncounterCancellation"):
            if form_def.programName and form_def.encounterTypeName:
                program_encounters.setdefault(form_def.programName, set()).add(
                    form_def.encounterTypeName
                )
        elif form_def.formType in ("Encounter", "IndividualEncounterCancellation"):
            if form_def.encounterTypeName:
                general_encounters.add(form_def.encounterTypeName)

    pe_mappings = [
        {"program": prog, "encounterTypes": sorted(ets)}
        for prog, ets in program_encounters.items()
    ]
    return pe_mappings, sorted(general_encounters)


def _find_primary_person_subject(srs: SRSData) -> str | None:
    """Find the primary Person-type subject type name from SRS data."""
    for st in srs.subjectTypes:
        name = st.get("name", "Individual")
        st_type = st.get("type", "Person")
        if st_type == "Person" or name == "Individual":
            return name
    # Fallback: first subject type
    if srs.subjectTypes:
        return srs.subjectTypes[0].get("name", "Individual")
    return "Individual"


def _auto_generate_cancellation_forms(
    srs: SRSData,
    concepts: ConceptManager,
    registry: UUIDRegistry,
) -> list[SRSFormDefinition]:
    """Auto-generate cancellation forms for every encounter type that has a form.

    Avni server requires a cancellation form for every schedulable encounter type.
    If the SRS doesn't include one, we generate a default with a "Cancel Reason" field.
    """
    existing_form_types = {
        (f.formType, f.encounterTypeName, f.programName)
        for f in srs.forms
    }

    primary_person_st = _find_primary_person_subject(srs)
    cancellation_forms: list[SRSFormDefinition] = []

    for form_def in srs.forms:
        # Use parent form's subject type, fallback to primary Person type
        subject_type = form_def.subjectTypeName or primary_person_st

        # ProgramEncounter → needs ProgramEncounterCancellation
        if form_def.formType == "ProgramEncounter" and form_def.encounterTypeName:
            cancel_key = ("ProgramEncounterCancellation", form_def.encounterTypeName, form_def.programName)
            if cancel_key not in existing_form_types:
                cancel_form = SRSFormDefinition(
                    name=f"{form_def.encounterTypeName} Cancellation",
                    formType="ProgramEncounterCancellation",
                    programName=form_def.programName,
                    encounterTypeName=form_def.encounterTypeName,
                    subjectTypeName=subject_type,
                    groups=[SRSFormGroup(
                        name="Cancellation Details",
                        fields=[
                            SRSFormField(
                                name="Cancel Reason",
                                dataType="Coded",
                                mandatory=True,
                                options=["Not available", "Migrated", "Refused", "Other"],
                                type="SingleSelect",
                            ),
                        ],
                    )],
                )
                cancellation_forms.append(cancel_form)
                existing_form_types.add(cancel_key)

        # Encounter (general) → needs IndividualEncounterCancellation
        if form_def.formType == "Encounter" and form_def.encounterTypeName:
            cancel_key = ("IndividualEncounterCancellation", form_def.encounterTypeName, None)
            if cancel_key not in existing_form_types:
                cancel_form = SRSFormDefinition(
                    name=f"{form_def.encounterTypeName} Cancellation",
                    formType="IndividualEncounterCancellation",
                    encounterTypeName=form_def.encounterTypeName,
                    subjectTypeName=subject_type,
                    groups=[SRSFormGroup(
                        name="Cancellation Details",
                        fields=[
                            SRSFormField(
                                name="Cancel Reason",
                                dataType="Coded",
                                mandatory=True,
                                options=["Not available", "Migrated", "Refused", "Other"],
                                type="SingleSelect",
                            ),
                        ],
                    )],
                )
                cancellation_forms.append(cancel_form)
                existing_form_types.add(cancel_key)

    return cancellation_forms


def _auto_generate_exit_forms(
    srs: SRSData,
    concepts: ConceptManager,
    registry: UUIDRegistry,
) -> list[SRSFormDefinition]:
    """Auto-generate exit/enrolment exit forms for every program that has an enrolment form.

    Avni server requires a ProgramExit form for every program.
    """
    existing_form_types = {
        (f.formType, f.programName)
        for f in srs.forms
    }

    primary_person_st = _find_primary_person_subject(srs)
    exit_forms: list[SRSFormDefinition] = []

    for form_def in srs.forms:
        if form_def.formType == "ProgramEnrolment" and form_def.programName:
            exit_key = ("ProgramExit", form_def.programName)
            if exit_key not in existing_form_types:
                subject_type = form_def.subjectTypeName or primary_person_st
                exit_form = SRSFormDefinition(
                    name=f"{form_def.programName} Exit",
                    formType="ProgramExit",
                    programName=form_def.programName,
                    subjectTypeName=subject_type,
                    groups=[SRSFormGroup(
                        name="Exit Details",
                        fields=[
                            SRSFormField(
                                name="Exit Reason",
                                dataType="Coded",
                                mandatory=True,
                                options=["Completed", "Dropped out", "Migrated", "Death", "Other"],
                                type="SingleSelect",
                            ),
                            SRSFormField(
                                name="Exit Date",
                                dataType="Date",
                                mandatory=True,
                            ),
                        ],
                    )],
                )
                exit_forms.append(exit_form)
                existing_form_types.add(exit_key)

    return exit_forms


# ── Bundle Validation ─────────────────────────────────────────────────────────

VALID_DATA_TYPES = {
    "Numeric", "Text", "Coded", "Date", "DateTime", "Time",
    "Duration", "Image", "ImageV2", "Video", "Audio", "File", "Id",
    "NA", "Notes", "Location", "PhoneNumber", "GroupAffiliation",
    "Subject", "Encounter", "QuestionGroup",
}

VALID_FORM_TYPES = {
    "BeneficiaryIdentification", "IndividualProfile",
    "SubjectEnrolmentEligibility", "ManualProgramEnrolmentEligibility",
    "ProgramEnrolment", "ProgramExit",
    "ProgramEncounter", "ProgramEncounterCancellation",
    "Encounter", "IndividualEncounterCancellation",
    "ChecklistItem", "IndividualRelationship",
    "Location", "Task",
}

VALID_FORM_ELEMENT_TYPES = {
    "SingleSelect", "MultiSelect",
}

VALID_SUBJECT_TYPES = {"Person", "Individual", "Household", "Group", "User"}


# TODO: possibly unused -- validation has been moved to preflight_validator.py
class BundleValidationResult:
    """Collects validation errors and warnings for a generated bundle."""

    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"{len(self.errors)} error(s):")
            for e in self.errors:
                lines.append(f"  ERROR: {e}")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warning(s):")
            for w in self.warnings:
                lines.append(f"  WARN: {w}")
        if not lines:
            lines.append("Bundle validation passed — no issues found.")
        return "\n".join(lines)


# TODO: possibly unused -- superseded by preflight_validator.PreFlightValidator
def validate_bundle(bundle_dir: str) -> BundleValidationResult:
    """Validate a generated bundle directory against avni-server's expected schema.

    Checks:
    - All required files exist
    - Valid JSON in each file
    - Required fields present in each entity
    - Valid enum values (dataType, formType, subjectType)
    - No duplicate displayOrder within a form element group
    - No duplicate concept in same form
    - UUID format validity
    - Form mappings reference existing forms, programs, encounter types
    """
    result = BundleValidationResult()

    def _read_json(filename: str) -> Any | None:
        filepath = os.path.join(bundle_dir, filename)
        if not os.path.isfile(filepath):
            result.error(f"Missing required file: {filename}")
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            result.error(f"Invalid JSON in {filename}: {e}")
            return None

    def _is_valid_uuid(val: str) -> bool:
        try:
            uuid.UUID(val)
            return True
        except (ValueError, AttributeError):
            return False

    # 1. Required files
    required_files = [
        "subjectTypes.json", "operationalSubjectTypes.json",
        "concepts.json", "formMappings.json",
    ]
    for rf in required_files:
        if not os.path.isfile(os.path.join(bundle_dir, rf)):
            result.error(f"Missing required file: {rf}")

    # 2. Validate concepts
    concepts_data = _read_json("concepts.json")
    concept_uuids: set[str] = set()
    concept_names: set[str] = set()
    if isinstance(concepts_data, list):
        for i, concept in enumerate(concepts_data):
            name = concept.get("name", "")
            dt = concept.get("dataType", "")
            c_uuid = concept.get("uuid", "")

            if not name:
                result.error(f"Concept [{i}] missing 'name'")
            if dt and dt not in VALID_DATA_TYPES:
                result.error(f"Concept '{name}' has invalid dataType: '{dt}' (valid: {VALID_DATA_TYPES})")
            if c_uuid and not _is_valid_uuid(c_uuid):
                result.error(f"Concept '{name}' has invalid UUID: '{c_uuid}'")
            if c_uuid:
                if c_uuid in concept_uuids:
                    result.error(f"Duplicate concept UUID: '{c_uuid}' (concept: '{name}')")
                concept_uuids.add(c_uuid)
            if name:
                if name in concept_names:
                    result.error(f"Duplicate concept name: '{name}' — server will reject with DataIntegrityViolationException on concept_name_orgid unique constraint")
                concept_names.add(name)

            # Validate coded answers
            if dt == "Coded":
                answers = concept.get("answers", [])
                answer_orders = set()
                for a in answers:
                    a_order = a.get("order")
                    if a_order is not None and a_order in answer_orders:
                        result.warn(f"Concept '{name}' has duplicate answer order: {a_order}")
                    if a_order is not None:
                        answer_orders.add(a_order)

    # 3. Validate subject types
    st_data = _read_json("subjectTypes.json")
    st_uuids: set[str] = set()
    if isinstance(st_data, list):
        for st in st_data:
            st_type = st.get("type", "")
            if st_type and st_type not in VALID_SUBJECT_TYPES:
                result.warn(f"SubjectType '{st.get('name')}' has unusual type: '{st_type}'")
            if st.get("uuid"):
                st_uuids.add(st["uuid"])

    # 4. Validate forms
    forms_dir = os.path.join(bundle_dir, "forms")
    form_uuids: set[str] = set()
    if os.path.isdir(forms_dir):
        for form_file in os.listdir(forms_dir):
            if not form_file.endswith(".json"):
                continue
            form_data = _read_json(f"forms/{form_file}")
            if not isinstance(form_data, dict):
                continue

            form_name = form_data.get("name", form_file)
            form_type = form_data.get("formType", "")
            f_uuid = form_data.get("uuid", "")

            if form_type and form_type not in VALID_FORM_TYPES:
                result.error(f"Form '{form_name}' has invalid formType: '{form_type}'")
            if f_uuid:
                if f_uuid in form_uuids:
                    result.error(f"Duplicate form UUID: '{f_uuid}' (form: '{form_name}')")
                form_uuids.add(f_uuid)

            # Validate form element groups
            concept_names_in_form: set[str] = set()
            for feg in form_data.get("formElementGroups", []):
                display_orders_in_group: set[float] = set()
                for fe in feg.get("formElements", []):
                    fe_name = fe.get("name", "")
                    fe_type = fe.get("type", "")
                    d_order = fe.get("displayOrder")

                    if fe_type and fe_type not in VALID_FORM_ELEMENT_TYPES:
                        result.warn(f"Form '{form_name}', element '{fe_name}' has unusual type: '{fe_type}'")

                    if d_order is not None:
                        if d_order in display_orders_in_group:
                            result.error(
                                f"Form '{form_name}', group '{feg.get('name', '')}': "
                                f"duplicate displayOrder {d_order} for element '{fe_name}'"
                            )
                        display_orders_in_group.add(d_order)

                    # Check for duplicate concept in same form (server check F2)
                    concept_name = fe.get("concept", {}).get("name", "")
                    if concept_name:
                        if concept_name in concept_names_in_form:
                            result.error(
                                f"Form '{form_name}': concept '{concept_name}' appears multiple times — "
                                f"server will reject with InvalidObjectException('Cannot use same concept twice')"
                            )
                        concept_names_in_form.add(concept_name)

    # 4b. Validate form element concepts exist in concepts.json
    if os.path.isdir(forms_dir) and concept_uuids:
        for form_file in os.listdir(forms_dir):
            if not form_file.endswith(".json"):
                continue
            form_data = _read_json(f"forms/{form_file}")
            if not isinstance(form_data, dict):
                continue
            form_name = form_data.get("name", form_file)
            for feg in form_data.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    fe_concept_uuid = fe.get("concept", {}).get("uuid", "")
                    if fe_concept_uuid and fe_concept_uuid not in concept_uuids:
                        result.error(
                            f"Form '{form_name}', element '{fe.get('name', '')}': "
                            f"concept UUID '{fe_concept_uuid}' not in concepts.json"
                        )

    # 5. Validate form mappings
    fm_data = _read_json("formMappings.json")
    program_uuids: set[str] = set()
    et_uuids: set[str] = set()
    programs_data = _read_json("programs.json")
    if isinstance(programs_data, list):
        for prog in programs_data:
            if prog.get("uuid"):
                program_uuids.add(prog["uuid"])
    et_data_pre = _read_json("encounterTypes.json")
    if isinstance(et_data_pre, list):
        for et in et_data_pre:
            if et.get("uuid"):
                et_uuids.add(et["uuid"])

    if isinstance(fm_data, list):
        for fm in fm_data:
            fm_form_uuid = fm.get("formUUID", "")
            if fm_form_uuid and fm_form_uuid not in form_uuids:
                result.error(f"FormMapping '{fm.get('formName', '')}' references unknown form UUID")
            fm_type = fm.get("formType", "")
            if fm_type and fm_type not in VALID_FORM_TYPES:
                result.error(f"FormMapping '{fm.get('formName', '')}' has invalid formType: '{fm_type}'")
            fm_prog = fm.get("programUUID", "")
            if fm_prog and fm_prog not in program_uuids:
                result.error(f"FormMapping '{fm.get('formName', '')}' references unknown program UUID")
            fm_et = fm.get("encounterTypeUUID", "")
            if fm_et and fm_et not in et_uuids:
                result.error(f"FormMapping '{fm.get('formName', '')}' references unknown encounter type UUID")

    # 6. Validate programs
    if isinstance(programs_data, list):
        for prog in programs_data:
            if not prog.get("name"):
                result.error("Program missing 'name'")
            if not prog.get("colour"):
                result.warn(f"Program '{prog.get('name')}' missing 'colour'")

    # 7. Validate encounter types
    et_data = _read_json("encounterTypes.json")
    if isinstance(et_data, list):
        for et in et_data:
            if not et.get("name"):
                result.error("EncounterType missing 'name'")

    return result


# TODO: possibly unused -- error analysis is now in bundle_regenerator.py
def analyze_error_csv(error_content: str) -> dict[str, Any]:
    """Analyze an error CSV from a failed avni-server bundle upload.

    Parses the error output and provides fix suggestions for each error.
    Returns structured analysis with errors and suggested fixes.
    """
    import csv
    import io

    analysis: dict[str, Any] = {
        "total_errors": 0,
        "error_categories": {},
        "errors": [],
        "suggested_fixes": [],
    }

    # Common avni-server error patterns and their fixes
    error_patterns = {
        "Concept with name .* not found": {
            "category": "missing_concept",
            "fix": "Add the missing concept to concepts.json with the correct dataType",
        },
        "Duplicate concept name": {
            "category": "duplicate_concept",
            "fix": "Remove duplicate concept definitions — ensure each concept name is unique",
        },
        "Invalid form type": {
            "category": "invalid_form_type",
            "fix": "Use valid form types: IndividualProfile, Encounter, ProgramEncounter, ProgramEnrolment, ProgramExit, ProgramEncounterCancellation, IndividualEncounterCancellation",
        },
        "Subject type .* not found": {
            "category": "missing_subject_type",
            "fix": "Ensure the subject type is defined in subjectTypes.json before it's referenced",
        },
        "Program .* not found": {
            "category": "missing_program",
            "fix": "Ensure the program is defined in programs.json before it's referenced in forms or mappings",
        },
        "Encounter type .* not found": {
            "category": "missing_encounter_type",
            "fix": "Ensure the encounter type is defined in encounterTypes.json before it's referenced",
        },
        "already exists": {
            "category": "duplicate_entity",
            "fix": "Use the same UUID as the existing entity to update it, or choose a different name",
        },
        "displayOrder.*duplicate": {
            "category": "duplicate_display_order",
            "fix": "Ensure displayOrder values are unique within each form element group",
        },
        "UUID.*invalid": {
            "category": "invalid_uuid",
            "fix": "Ensure all UUIDs are valid v4 UUIDs (format: xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx)",
        },
        "data type.*mismatch": {
            "category": "datatype_mismatch",
            "fix": "Ensure the concept dataType matches its usage — Coded concepts need answers, Numeric needs unit/ranges",
        },
    }

    # Try parsing as CSV
    try:
        reader = csv.reader(io.StringIO(error_content))
        rows = list(reader)
    except Exception:
        # If not CSV, treat as line-separated errors
        rows = [[line] for line in error_content.strip().split("\n")]

    for row in rows:
        error_text = " ".join(str(cell) for cell in row).strip()
        if not error_text:
            continue

        analysis["total_errors"] += 1
        matched = False

        for pattern, info in error_patterns.items():
            if re.search(pattern, error_text, re.IGNORECASE):
                category = info["category"]
                analysis["error_categories"].setdefault(category, 0)
                analysis["error_categories"][category] += 1
                analysis["errors"].append({
                    "text": error_text,
                    "category": category,
                    "fix": info["fix"],
                })
                if info["fix"] not in analysis["suggested_fixes"]:
                    analysis["suggested_fixes"].append(info["fix"])
                matched = True
                break

        if not matched:
            analysis["errors"].append({
                "text": error_text,
                "category": "unknown",
                "fix": "Review the error message and check the corresponding JSON file for issues",
            })
            analysis["error_categories"].setdefault("unknown", 0)
            analysis["error_categories"]["unknown"] += 1

    return analysis


def _generate_placeholder_files(bundle_dir: str) -> None:
    """Generate empty placeholder files required by Avni server's import order.

    Every file in the server's BundleZipFileImporter.fileSequence must exist,
    even if empty. Missing files are silently skipped by the server but having
    them ensures consistent zip ordering and prevents edge-case issues.
    """
    # All optional files that need empty defaults if not already generated
    placeholders: dict[str, Any] = {
        "organisationConfig.json": {"settings": {}, "worklistUpdationRule": ""},
        "documentations.json": [],
        "individualRelation.json": [],
        "relationshipType.json": [],
        "identifierSource.json": [],
        "checklist.json": [],
        "groupRole.json": [],
        "video.json": [],
        "reportCard.json": [],
        "reportDashboard.json": [],
        "groupDashboards.json": [],
        "taskType.json": [],
        "taskStatus.json": [],
        "menuItem.json": [],
        "messageRule.json": [],
        "ruleDependency.json": [],
        "customQueries.json": [],
    }
    # Ensure translations directory with empty en.json
    translations_dir = os.path.join(bundle_dir, "translations")
    os.makedirs(translations_dir, exist_ok=True)
    en_path = os.path.join(translations_dir, "en.json")
    if not os.path.isfile(en_path):
        with open(en_path, "w", encoding="utf-8") as f:
            json.dump({}, f)

    for filename, default_content in placeholders.items():
        filepath = os.path.join(bundle_dir, filename)
        if not os.path.isfile(filepath):
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(_format_json(default_content))


def create_bundle_zip(output_dir: str, bundle_id: str) -> str:
    """Create an ordered zip file from the generated bundle files.

    Returns the path to the zip file.

    CRITICAL: With chunk=1, the server processes files in ZIP ENTRY ORDER,
    NOT the hardcoded fileSequence order. So the zip must be created with
    files in the exact dependency order from BundleZipFileImporter.fileSequence.

    See BUNDLE_GAP_ANALYSIS.md Section 5.2 — chunk=1 means zip order IS
    processing order.
    """
    zip_path = os.path.join(output_dir, f"{bundle_id}.zip")
    bundle_dir = os.path.join(output_dir, bundle_id)

    # Generate placeholder files before zipping
    _generate_placeholder_files(bundle_dir)

    # Exact order from avni-server BundleZipFileImporter.fileSequence (36 entries)
    # Every file listed here, even if empty, to ensure consistent processing.
    ordered_files: list[str] = [
        # 1. Organisation config (no deps)
        "organisationConfig.json",
        # 2. Address hierarchy (no deps)
        "addressLevelTypes.json",
        # 3-4. Locations & catchments (depend on addressLevelTypes)
        # (not generated by SRS bundles — only for location-heavy orgs)
        # 5-6. Subject types + operational wrappers
        "subjectTypes.json",
        "operationalSubjectTypes.json",
        # 7-8. Programs + operational wrappers
        "programs.json",
        "operationalPrograms.json",
        # 9-10. Encounter types + operational wrappers
        "encounterTypes.json",
        "operationalEncounterTypes.json",
        # 11. Documentations
        "documentations.json",
        # 12. Concepts (answers resolved inline, no deps on forms)
        "concepts.json",
    ]

    # 13. Forms (each file separately — depend on concepts)
    forms_dir = os.path.join(bundle_dir, "forms")
    if os.path.isdir(forms_dir):
        form_files = sorted(
            f for f in os.listdir(forms_dir) if f.endswith(".json")
        )
        for f in form_files:
            ordered_files.append(os.path.join("forms", f))

    # 14-36. Remaining files in exact server dependency order
    ordered_files.extend([
        "formMappings.json",           # 14. depends on forms, subjectTypes, programs, encounterTypes
        "individualRelation.json",     # 15. no deps
        "relationshipType.json",       # 16. depends on individualRelation
        "identifierSource.json",       # 17. no deps
        "checklist.json",              # 18. depends on concepts
        "groups.json",                 # 19. no deps
        "groupRole.json",             # 20. depends on groups, subjectTypes
        "groupPrivilege.json",        # 21. depends on groups, subjectTypes, programs, encounterTypes
        "video.json",                  # 22. no deps
        "reportCard.json",            # 23. no deps
        "reportDashboard.json",       # 24. depends on reportCard
        "groupDashboards.json",       # 25. depends on reportDashboard, groups
        "taskType.json",              # 26. no deps
        "taskStatus.json",            # 27. depends on taskType
        "menuItem.json",              # 28. depends on forms
        "messageRule.json",           # 29. depends on subjectTypes, programs, encounterTypes
    ])

    # 30. Translations
    translations_dir = os.path.join(bundle_dir, "translations")
    if os.path.isdir(translations_dir):
        for tf in sorted(os.listdir(translations_dir)):
            if tf.endswith(".json"):
                ordered_files.append(os.path.join("translations", tf))

    # 31. Rule dependency
    ordered_files.append("ruleDependency.json")

    # 32-35. Directories (oldRules, subjectTypeIcons, reportCardIcons, conceptMedia)
    # — not generated by SRS bundles

    # 36. Custom queries
    ordered_files.append("customQueries.json")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in ordered_files:
            full_path = os.path.join(bundle_dir, rel_path)
            if os.path.isfile(full_path):
                zf.write(full_path, rel_path)

    return zip_path


async def generate_from_srs(srs: SRSData, bundle_id: str) -> str:
    """Main orchestrator: generate all bundle files from SRS data.

    Returns the path to the generated zip file.
    """
    _bundle_store[bundle_id] = BundleStatus(
        id=bundle_id,
        status=BundleStatusType.GENERATING,
        progress=0,
        message="Starting bundle generation...",
    )

    try:
        output_base = settings.BUNDLE_OUTPUT_DIR
        bundle_dir = os.path.join(output_base, bundle_id)
        forms_dir = os.path.join(bundle_dir, "forms")
        os.makedirs(forms_dir, exist_ok=True)

        registry = UUIDRegistry()
        concepts = ConceptManager(registry)

        def _write(filename: str, data: Any) -> None:
            filepath = os.path.join(bundle_dir, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(_format_json(data))

        # 1. Address level types
        _update_status(bundle_id, 5, "Generating address level types...")
        address_level_types = generate_address_level_types(srs, registry)
        _write("addressLevelTypes.json", address_level_types)

        # 2. Subject types
        _update_status(bundle_id, 10, "Generating subject types...")
        subject_types = generate_subject_types(srs, registry)
        _write("subjectTypes.json", subject_types)
        # Prefer "Individual" or "Person" type as primary (not just first in list)
        primary_st_uuid = subject_types[0]["uuid"]
        for st in subject_types:
            if st["type"] == "Person" or st["name"] == "Individual":
                primary_st_uuid = st["uuid"]
                break

        # 3. Operational subject types
        _update_status(bundle_id, 15, "Generating operational subject types...")
        op_subject_types = generate_operational_subject_types(subject_types, registry)
        _write("operationalSubjectTypes.json", op_subject_types)

        # 4. Programs (before encounter types — matches server fileSequence order)
        _update_status(bundle_id, 20, "Generating programs...")
        programs = generate_programs(srs, registry)
        _write("programs.json", programs)

        # 5. Operational programs
        _update_status(bundle_id, 25, "Generating operational programs...")
        op_programs = generate_operational_programs(programs, registry)
        _write("operationalPrograms.json", op_programs)

        # 6. Encounter types
        _update_status(bundle_id, 30, "Generating encounter types...")
        encounter_types = generate_encounter_types(srs, registry)
        _write("encounterTypes.json", encounter_types)

        # 7. Operational encounter types
        _update_status(bundle_id, 35, "Generating operational encounter types...")
        op_encounter_types = generate_operational_encounter_types(
            encounter_types, registry
        )
        _write("operationalEncounterTypes.json", op_encounter_types)

        # 7b. Auto-generate cancellation and exit forms
        _update_status(bundle_id, 38, "Auto-generating cancellation & exit forms...")
        auto_cancel_forms = _auto_generate_cancellation_forms(srs, concepts, registry)
        auto_exit_forms = _auto_generate_exit_forms(srs, concepts, registry)
        all_forms = list(srs.forms) + auto_cancel_forms + auto_exit_forms
        if auto_cancel_forms or auto_exit_forms:
            logger.info(
                "Auto-generated %d cancellation form(s) and %d exit form(s)",
                len(auto_cancel_forms), len(auto_exit_forms),
            )
            # Also ensure encounter types include any from auto-generated forms
            existing_et_names = {et["name"] for et in encounter_types}
            for f in auto_cancel_forms + auto_exit_forms:
                if f.encounterTypeName and f.encounterTypeName not in existing_et_names:
                    existing_et_names.add(f.encounterTypeName)

        # 7c. Inject eligibility rules into programs (before writing)
        if srs.eligibilityRules:
            _update_status(bundle_id, 39, "Generating eligibility rules...")
            for rule_def in srs.eligibilityRules:
                prog_name = rule_def.get("program", "")
                condition = rule_def.get("condition", "")
                if not prog_name or not condition:
                    continue
                for prog in programs:
                    if prog["name"] == prog_name:
                        prog["enrolmentEligibilityCheckRule"] = _generate_eligibility_rule_js(condition)
                        logger.info("Generated eligibility rule for program '%s'", prog_name)
                        break
            # Re-write programs.json with eligibility rules
            _write("programs.json", programs)

        # 8. Forms (and build concept registry along the way)
        _update_status(bundle_id, 40, "Generating forms and rules...")
        rule_injector = RuleInjector(concepts, registry, all_forms, srs.visitSchedules)

        # Group SRS decisions by form name for injection
        decisions_by_form: dict[str, list[dict[str, Any]]] = {}
        if srs.decisions:
            for d in srs.decisions:
                decisions_by_form.setdefault(d["formName"], []).append(d)

        form_meta: list[dict[str, Any]] = []
        total_forms = len(all_forms)

        for i, form_def in enumerate(all_forms):
            form_uuid = registry.stable_uuid(f"form:{form_def.name}")
            form_json = _build_form(form_def, form_uuid, concepts, registry, rule_injector)

            # Inject decision rule JS from Decisions sheet
            form_decisions = decisions_by_form.get(form_def.name, [])
            if form_decisions:
                decision_js = _generate_decision_rule_js(form_decisions, form_def.formType, concepts)
                if decision_js:
                    form_json["decisionRule"] = decision_js
                    logger.info("Generated decision rule for form '%s' (%d decisions)", form_def.name, len(form_decisions))

            _write(f"forms/{_sanitize_filename(form_def.name)}.json", form_json)

            meta: dict[str, Any] = {
                "formUUID": form_uuid,
                "formType": form_def.formType,
                "formName": form_def.name,
            }
            if form_def.programName:
                meta["programUUID"] = registry.stable_uuid(
                    f"program:{form_def.programName}"
                )
            if form_def.encounterTypeName:
                meta["encounterTypeUUID"] = registry.stable_uuid(
                    f"encounterType:{form_def.encounterTypeName}"
                )
            # Resolve subject type UUID from form's subjectTypeName
            _resolved_st_name = form_def.subjectTypeName

            # For registration forms (IndividualProfile) without a subjectTypeName,
            # infer the subject type from the form name (e.g. "Family Registration" → "Family")
            if not _resolved_st_name and form_def.formType == "IndividualProfile":
                _st_names_lower = {st["name"].lower(): st["name"] for st in subject_types}
                _form_name_lower = form_def.name.lower()
                for _st_lower, _st_name in _st_names_lower.items():
                    if _st_lower in _form_name_lower:
                        _resolved_st_name = _st_name
                        break

            if _resolved_st_name:
                st_uuid = registry.stable_uuid(f"subjectType:{_resolved_st_name}")
                # Verify it's a known subject type
                known_st_uuids = {st["uuid"] for st in subject_types}
                if st_uuid in known_st_uuids:
                    meta["subjectTypeUUID"] = st_uuid
            form_meta.append(meta)

            progress = 40 + int(30 * (i + 1) / max(total_forms, 1))
            _update_status(
                bundle_id, progress, f"Generated form {i + 1}/{total_forms}: {form_def.name}"
            )

        # 9. Concepts (collected from all forms)
        _update_status(bundle_id, 75, "Generating concepts...")

        # Pre-generation validation: check for name collisions (server error C7)
        collision_errors = concepts.validate_no_name_collisions()
        for err in collision_errors:
            logger.error("Bundle %s: %s", bundle_id, err)

        concepts_list = concepts.all_concepts()

        # Post-generation validation: check name lengths (server error F7: max 255)
        for c in concepts_list:
            if len(c["name"]) > 255:
                logger.error(
                    "Bundle %s: Concept name exceeds 255 chars: '%s...'",
                    bundle_id, c["name"][:50],
                )

        _write("concepts.json", concepts_list)

        # 10. Form mappings
        _update_status(bundle_id, 80, "Generating form mappings...")
        form_mappings = generate_form_mappings(form_meta, primary_st_uuid, registry)
        _write("formMappings.json", form_mappings)

        # 11. Groups
        _update_status(bundle_id, 85, "Generating groups...")
        groups = generate_groups(srs.groups, registry)
        _write("groups.json", groups)

        # 12. Group privileges
        _update_status(bundle_id, 90, "Generating group privileges...")
        pe_mappings, ge_types = _infer_program_encounter_mappings(srs, registry)
        group_privileges = generate_group_privileges(
            srs.groups, primary_st_uuid, programs,
            pe_mappings, ge_types, registry,
        )
        _write("groupPrivilege.json", group_privileges)

        # 12b. Report cards + dashboard
        if srs.reportCards:
            _update_status(bundle_id, 91, "Generating report cards and dashboard...")
            report_cards, report_dashboard, group_dashboards = generate_report_cards(
                srs.reportCards, registry, subject_types, programs, encounter_types,
            )
            _write("reportCard.json", report_cards)
            _write("reportDashboard.json", report_dashboard)
            _write("groupDashboards.json", group_dashboards)
            logger.info("Generated %d report cards with dashboard", len(report_cards))

        # 13. Validate bundle (unified 6-layer pre-flight validation)
        _update_status(bundle_id, 93, "Validating bundle...")
        from app.services.preflight_validator import PreFlightValidator
        pf_validator = PreFlightValidator()
        pf_result = pf_validator.validate(bundle_dir)
        if pf_result.errors:
            logger.warning(
                "Bundle %s has %d validation error(s):\n%s",
                bundle_id, len(pf_result.errors), pf_result.summary(),
            )
        if pf_result.warnings:
            logger.info(
                "Bundle %s has %d validation warning(s)", bundle_id, len(pf_result.warnings),
            )

        # 13b. Server contract validation (mirrors avni-server's BundleZipFileImporter)
        _update_status(bundle_id, 95, "Validating against server contracts...")
        from app.services.server_contract_validator import validate_bundle as validate_server_contracts
        contract_result = validate_server_contracts(bundle_dir)
        if contract_result.errors:
            logger.warning(
                "Bundle %s has %d server contract error(s):\n%s",
                bundle_id, len(contract_result.errors), contract_result.summary(),
            )
        if contract_result.warnings:
            logger.info(
                "Bundle %s has %d server contract warning(s)",
                bundle_id, len(contract_result.warnings),
            )

        # 13c. Comprehensive bundle validation (12-point check ported from bundle_validator.js)
        _update_status(bundle_id, 96, "Running comprehensive bundle validation...")
        from app.services.bundle_validator import validate_bundle as validate_bundle_comprehensive
        bundle_validation_result = validate_bundle_comprehensive(bundle_dir)
        # Write validation report to bundle directory
        with open(os.path.join(bundle_dir, "validation_report.json"), "w") as f:
            json.dump(bundle_validation_result, f, indent=2)
        if bundle_validation_result.get("errors"):
            logger.warning(
                "Bundle %s comprehensive validation found %d error(s)",
                bundle_id, len(bundle_validation_result["errors"]),
            )
        if bundle_validation_result.get("warnings"):
            logger.info(
                "Bundle %s comprehensive validation found %d warning(s)",
                bundle_id, len(bundle_validation_result["warnings"]),
            )

        # 14. Create zip (always create for debugging, even if validation fails)
        _update_status(bundle_id, 97, "Creating zip file...")
        zip_path = create_bundle_zip(settings.BUNDLE_OUTPUT_DIR, bundle_id)

        total_errors = (
            len(pf_result.errors)
            + len(contract_result.errors)
            + len(bundle_validation_result.get("errors", []))
        )
        total_warnings = (
            len(pf_result.warnings)
            + len(contract_result.warnings)
            + len(bundle_validation_result.get("warnings", []))
        )

        auto_forms_note = ""
        if auto_cancel_forms or auto_exit_forms:
            auto_forms_note = (
                f" (incl. {len(auto_cancel_forms)} auto-cancellation, "
                f"{len(auto_exit_forms)} auto-exit)"
            )

        rule_stats = rule_injector.stats
        total_rules = sum(rule_stats.values())
        rules_note = f", {total_rules} rules" if total_rules else ""
        if total_rules:
            rule_parts = []
            if rule_stats["skip_logic"]:
                rule_parts.append(f"{rule_stats['skip_logic']} skip-logic")
            if rule_stats["visit_schedule"]:
                rule_parts.append(f"{rule_stats['visit_schedule']} visit-schedule")
            if rule_stats["cancel_reschedule"]:
                rule_parts.append(f"{rule_stats['cancel_reschedule']} cancel-reschedule")
            if rule_stats["validation"]:
                rule_parts.append(f"{rule_stats['validation']} numeric-validation")
            if rule_stats["date_validation"]:
                rule_parts.append(f"{rule_stats['date_validation']} date-validation")
            if rule_stats["feg_rule"]:
                rule_parts.append(f"{rule_stats['feg_rule']} FEG-visibility")
            rules_note = f", {total_rules} rules ({', '.join(rule_parts)})"

        logger.info(
            "Bundle %s rule generation stats: %s", bundle_id, rule_stats,
        )

        # ── HARD GATE: Block download if server contract validation fails ──
        if total_errors > 0:
            # Extract human-readable message from error objects
            def _err_msg(e: Any) -> str:
                if hasattr(e, 'message'):
                    msg = e.message
                    if hasattr(e, 'fix_hint') and e.fix_hint:
                        msg += f" (fix: {e.fix_hint})"
                    return msg
                return str(e)

            all_errors = [_err_msg(e) for e in pf_result.errors + contract_result.errors]
            # Deduplicate similar messages
            seen = set()
            unique_errors = []
            for e in all_errors:
                key = e[:80]
                if key not in seen:
                    seen.add(key)
                    unique_errors.append(e)
            all_errors = unique_errors

            error_summary = "\n".join(f"  - {e}" for e in all_errors[:10])
            if len(all_errors) > 10:
                error_summary += f"\n  ... and {len(all_errors) - 10} more"

            # Still mark as COMPLETED but include error summary in message
            # so user can see what's wrong and decide whether to upload or fix
            logger.warning(
                "Bundle %s has %d validation error(s):\n%s",
                bundle_id, total_errors, error_summary,
            )
            validation_note = f" | {total_errors} validation error(s) — review before uploading"

        # ── Validation summary ──
        if total_errors == 0:
            validation_note = ""
            if total_warnings:
                validation_note = f" | {total_warnings} warning(s)"

        _bundle_store[bundle_id] = BundleStatus(
            id=bundle_id,
            status=BundleStatusType.COMPLETED,
            progress=100,
            message=f"Bundle generated: {len(concepts_list)} concepts, "
                    f"{total_forms} forms{auto_forms_note}, {len(form_mappings)} mappings, "
                    f"{len(group_privileges)} privileges{rules_note}{validation_note}",
            download_url=f"/api/bundle/{bundle_id}/download",
        )

        return zip_path

    except Exception as e:
        logger.exception("Bundle generation failed for %s", bundle_id)
        _bundle_store[bundle_id] = BundleStatus(
            id=bundle_id,
            status=BundleStatusType.FAILED,
            progress=0,
            message="Bundle generation failed",
            error=str(e),
        )
        raise


def _update_status(bundle_id: str, progress: int, message: str) -> None:
    if bundle_id in _bundle_store:
        _bundle_store[bundle_id].progress = progress
        _bundle_store[bundle_id].message = message


def get_bundle_status(bundle_id: str) -> BundleStatus | None:
    return _bundle_store.get(bundle_id)


def get_bundle_zip_path(bundle_id: str) -> str | None:
    zip_path = os.path.join(settings.BUNDLE_OUTPUT_DIR, f"{bundle_id}.zip")
    if os.path.isfile(zip_path):
        return zip_path
    return None


def get_bundle_file_tree(bundle_id: str) -> list[dict] | None:
    """Return the bundle's file tree with content previews for the frontend UI."""
    bundle_dir = os.path.join(settings.BUNDLE_OUTPUT_DIR, bundle_id)
    if not os.path.isdir(bundle_dir):
        return None

    def _build_tree(dir_path: str, rel_prefix: str = "") -> list[dict]:
        entries = []
        try:
            items = sorted(os.listdir(dir_path))
        except OSError:
            return entries

        # Directories first, then files
        dirs = [i for i in items if os.path.isdir(os.path.join(dir_path, i))]
        files = [i for i in items if os.path.isfile(os.path.join(dir_path, i))]

        for d in dirs:
            full = os.path.join(dir_path, d)
            rel = f"{rel_prefix}{d}" if not rel_prefix else f"{rel_prefix}/{d}"
            children = _build_tree(full, rel)
            entries.append({
                "name": d,
                "path": f"bundle/{rel}",
                "type": "directory",
                "status": "pass",
                "children": children,
            })

        for f in files:
            full = os.path.join(dir_path, f)
            rel = f"{rel_prefix}/{f}" if rel_prefix else f
            content = ""
            try:
                with open(full, "r") as fh:
                    raw = fh.read()
                    # Pretty-print JSON, truncate large files
                    try:
                        parsed = json.loads(raw)
                        content = json.dumps(parsed, indent=2)
                        if len(content) > 5000:
                            content = content[:5000] + "\n... (truncated)"
                    except json.JSONDecodeError:
                        content = raw[:5000]
            except OSError:
                content = "Could not read file"

            entries.append({
                "name": f,
                "path": f"bundle/{rel}",
                "type": "file",
                "status": "pass",
                "content": content,
            })

        return entries

    children = _build_tree(bundle_dir)
    return [{
        "name": "bundle",
        "path": "bundle",
        "type": "directory",
        "status": "pass",
        "children": children,
    }]
