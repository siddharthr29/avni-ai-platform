"""Clarity Engine — detect gaps in SRS data and ask targeted clarifying questions.

Runs deterministic structural analysis on parsed SRS data to find missing
entities, ambiguous concepts, incomplete rules, unclear schedules, unmapped
forms, and missing answers. No LLM dependency for core gap detection; RAG
is used only for generating smart suggestions from similar org bundles.

Design principle: helpful, not annoying. Only surface questions that would
cause generation failures (CRITICAL) or significantly degrade output quality
(IMPORTANT). NICE_TO_HAVE questions are included but can be auto-defaulted.

Usage:
    engine = ClarityEngine()
    questions = await engine.analyze(srs_data_dict)
    if not engine.can_proceed(questions):
        # present CRITICAL questions to user, collect answers
        ...
    patched = engine.apply_answers(srs_data_dict, answers)
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "ClarityEngine",
    "clarity_engine",
    "ClarityQuestion",
    "GapSeverity",
    "GapCategory",
]


# ---------------------------------------------------------------------------
# Enums & Data Classes
# ---------------------------------------------------------------------------

class GapSeverity(Enum):
    CRITICAL = "critical"       # Cannot generate without this info
    IMPORTANT = "important"     # Can generate but quality will be low
    NICE_TO_HAVE = "nice"       # Can infer/default but better to confirm


class GapCategory(Enum):
    MISSING_ENTITY = "missing_entity"
    AMBIGUOUS_CONCEPT = "ambiguous_concept"
    MISSING_RULE = "missing_rule"
    UNCLEAR_SCHEDULE = "unclear_schedule"
    MISSING_MAPPING = "missing_mapping"
    INCOMPLETE_FORM = "incomplete_form"
    MISSING_ANSWERS = "missing_answers"
    CONFLICTING_INFO = "conflicting_info"


# Severity ordering for sorting (lower index = higher priority)
_SEVERITY_ORDER = [GapSeverity.CRITICAL, GapSeverity.IMPORTANT, GapSeverity.NICE_TO_HAVE]


@dataclass
class ClarityQuestion:
    """A single gap-detection result with a human-readable question."""

    id: str
    category: GapCategory
    severity: GapSeverity
    question: str                        # Human-readable question
    context: str                         # Why we're asking (what SRS said)
    suggestions: list[str] = field(default_factory=list)
    default: Optional[str] = None        # What we'll use if user doesn't answer
    field_path: Optional[str] = None     # Which SRS field this relates to
    answer: Optional[str] = None         # Filled in when user responds


# ---------------------------------------------------------------------------
# Known Avni conventions for smart defaults & validation
# ---------------------------------------------------------------------------

_VALID_FORM_TYPES = {
    "IndividualProfile", "ProgramEnrolment", "ProgramExit",
    "ProgramEncounter", "ProgramEncounterCancellation",
    "Encounter", "IndividualEncounterCancellation",
    "ChecklistItem",
}

_VALID_DATA_TYPES = {
    "Text", "Numeric", "Date", "DateTime", "Time", "Coded",
    "Notes", "Image", "Video", "Audio", "File", "Id",
    "PhoneNumber", "GroupAffiliation", "Location", "Subject",
    "Encounter", "NA", "Duration", "QuestionGroup",
}

_SUBJECT_TYPE_TYPES = {"Person", "Individual", "Household", "Group"}

# Common concept names that frequently collide between question and answer
_COLLISION_RISK_NAMES = {
    "abortion", "hiv", "fever", "jaundice", "malaria", "anaemia",
    "diabetes", "pregnant", "disabled", "active", "hypertension",
    "tuberculosis", "tb", "anemia", "asthma", "epilepsy",
    "depression", "anxiety", "diarrhoea", "diarrhea", "pneumonia",
}

# Standard Yes/No answer UUIDs from production Avni
_STANDARD_YES_NO = {"Yes", "No"}

# Common coded fields that should use standard answers
_GENDER_FIELD_NAMES = {"gender", "sex", "biological sex"}
_YES_NO_FIELD_INDICATORS = {"is ", "has ", "does ", "was ", "were ", "did "}

# Vague schedule terms that need specifics
_VAGUE_SCHEDULE_TERMS = [
    r"\bregular\s+visit",
    r"\bperiodic\s+visit",
    r"\bfollow[\s-]?up\b",
    r"\broutine\s+visit",
    r"\bperiodic\s+check",
    r"\bas\s+needed\b",
    r"\bwhen\s+required\b",
]


def _qid() -> str:
    """Generate a short question ID."""
    return str(uuid.uuid4())[:8]


# ---------------------------------------------------------------------------
# ClarityEngine
# ---------------------------------------------------------------------------

class ClarityEngine:
    """Detects gaps in SRS data and generates targeted clarifying questions.

    Core analysis is fully deterministic (no LLM calls). RAG-based suggestions
    are optional and fetched asynchronously when available.
    """

    async def analyze(
        self,
        srs_data: dict[str, Any],
        org_context: dict[str, Any] | None = None,
    ) -> list[ClarityQuestion]:
        """Analyze SRS data for gaps and ambiguities.

        Args:
            srs_data: Dict representation of SRSData (from .model_dump() or raw JSON).
            org_context: Optional org info (sector, org_name) for context-aware checks.

        Returns:
            List of ClarityQuestions sorted by severity (CRITICAL first).
        """
        questions: list[ClarityQuestion] = []

        questions.extend(self._check_entity_completeness(srs_data))
        questions.extend(self._check_concept_clarity(srs_data))
        questions.extend(self._check_rule_completeness(srs_data))
        questions.extend(self._check_visit_schedules(srs_data))
        questions.extend(self._check_form_mappings(srs_data))
        questions.extend(self._check_answer_completeness(srs_data))
        questions.extend(self._check_conflicts(srs_data))

        # Sort: CRITICAL > IMPORTANT > NICE_TO_HAVE
        questions.sort(key=lambda q: _SEVERITY_ORDER.index(q.severity))

        # Attempt RAG-powered suggestions (non-blocking, best-effort)
        await self._enrich_suggestions(questions, srs_data, org_context)

        return questions

    def can_proceed(self, questions: list[ClarityQuestion]) -> bool:
        """Check if all CRITICAL questions have been answered or have defaults.

        Returns True if there are no unanswered CRITICAL questions, meaning
        bundle generation can proceed (possibly with reduced quality for
        unanswered IMPORTANT/NICE_TO_HAVE questions).
        """
        for q in questions:
            if q.severity == GapSeverity.CRITICAL:
                if q.answer is None and q.default is None:
                    return False
        return True

    def apply_answers(
        self,
        srs_data: dict[str, Any],
        answers: dict[str, str],
    ) -> dict[str, Any]:
        """Apply user's answers to fill gaps in SRS data.

        Args:
            srs_data: The original SRS data dict (will be copied, not mutated).
            answers: Mapping of question ID -> user's answer text.

        Returns:
            A new SRS data dict with gaps filled based on answers.
        """
        import copy
        patched = copy.deepcopy(srs_data)

        for qid, answer in answers.items():
            self._apply_single_answer(patched, qid, answer)

        return patched

    def format_for_chat(
        self,
        questions: list[ClarityQuestion],
        max_questions: int = 8,
    ) -> str:
        """Format questions as a conversational chat message.

        Groups by severity, limits total count to avoid overwhelming the user.
        Returns a markdown-formatted string ready for SSE streaming.
        """
        if not questions:
            return ""

        # Take up to max_questions, prioritizing CRITICAL
        selected = questions[:max_questions]

        critical = [q for q in selected if q.severity == GapSeverity.CRITICAL]
        important = [q for q in selected if q.severity == GapSeverity.IMPORTANT]
        nice = [q for q in selected if q.severity == GapSeverity.NICE_TO_HAVE]

        parts: list[str] = []
        parts.append(
            "Before generating the bundle, I need a few clarifications "
            "to ensure the output is accurate:\n"
        )

        if critical:
            parts.append("**Required (cannot proceed without these):**")
            for i, q in enumerate(critical, 1):
                parts.append(self._format_question(q, i))

        if important:
            label = len(critical) + 1
            parts.append("\n**Recommended (improves quality):**")
            for i, q in enumerate(important, label):
                parts.append(self._format_question(q, i))

        if nice:
            label = len(critical) + len(important) + 1
            parts.append("\n**Optional (I can use defaults):**")
            for i, q in enumerate(nice, label):
                default_note = f" *(default: {q.default})*" if q.default else ""
                parts.append(self._format_question(q, i) + default_note)

        remaining = len(questions) - len(selected)
        if remaining > 0:
            parts.append(f"\n*...and {remaining} more minor questions that I can handle with defaults.*")

        parts.append(
            "\nPlease answer what you can. For anything you skip, "
            "I'll use reasonable defaults based on similar implementations."
        )

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Gap Detection Checks
    # ------------------------------------------------------------------

    def _check_entity_completeness(self, srs: dict) -> list[ClarityQuestion]:
        """Check for missing or incomplete entity definitions."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])
        programs = srs.get("programs", [])
        encounter_types = srs.get("encounterTypes", [])
        subject_types = srs.get("subjectTypes", [])

        # --- No subject types at all ---
        if not subject_types:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.MISSING_ENTITY,
                severity=GapSeverity.CRITICAL,
                question="What type of beneficiaries will this program track?",
                context="No subject types are defined in the SRS.",
                suggestions=["Individual (Person)", "Household", "Group/Family"],
                default="Individual",
                field_path="subjectTypes",
            ))

        # --- Subject type without proper 'type' field ---
        for st in subject_types:
            st_name = st.get("name", "")
            st_type = st.get("type", "")
            if st_type and st_type not in _SUBJECT_TYPE_TYPES:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.MISSING_ENTITY,
                    severity=GapSeverity.IMPORTANT,
                    question=f"What kind of entity is '{st_name}'? Is it a Person, Household, or Group?",
                    context=f"Subject type '{st_name}' has type '{st_type}' which is not a standard Avni type.",
                    suggestions=list(_SUBJECT_TYPE_TYPES),
                    default="Person",
                    field_path=f"subjectTypes[name={st_name}].type",
                ))

        # --- Programs mentioned in forms but not in program list ---
        program_names = {p["name"] for p in programs if isinstance(p, dict) and "name" in p}
        form_program_refs = set()
        for form in forms:
            pn = form.get("programName")
            if pn:
                form_program_refs.add(pn)

        for ref in form_program_refs - program_names:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.MISSING_ENTITY,
                severity=GapSeverity.CRITICAL,
                question=f"Program '{ref}' is referenced in a form but not defined. Should it be added?",
                context=f"Form references program '{ref}' but it is not in the programs list.",
                suggestions=[f"Add '{ref}' as a program", "This is a typo, correct name is..."],
                field_path="programs",
            ))

        # --- Encounter types referenced in forms but not in encounterTypes list ---
        et_set = set(encounter_types) if isinstance(encounter_types, list) else set()
        # Also include encounter types from programEncounterMappings
        pem = srs.get("programEncounterMappings", []) or []
        for mapping in pem:
            for et in mapping.get("encounterTypes", []):
                et_set.add(et)

        form_et_refs = set()
        for form in forms:
            etn = form.get("encounterTypeName")
            if etn:
                form_et_refs.add(etn)

        for ref in form_et_refs - et_set:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.MISSING_ENTITY,
                severity=GapSeverity.IMPORTANT,
                question=f"Encounter type '{ref}' is used in a form but not listed in encounterTypes. Should it be added?",
                context=f"Form references encounter type '{ref}' but it's missing from the encounter types list.",
                suggestions=[f"Add '{ref}' as an encounter type"],
                default=f"Add '{ref}'",
                field_path="encounterTypes",
            ))

        # --- Programs without any encounter types ---
        if programs and not encounter_types and not pem:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.MISSING_ENTITY,
                severity=GapSeverity.CRITICAL,
                question="What visit/encounter types should be created for your programs?",
                context=(
                    f"Programs defined ({', '.join(p.get('name', '?') for p in programs if isinstance(p, dict))}) "
                    "but no encounter types are listed."
                ),
                suggestions=[
                    "Home Visit, Follow-up Visit",
                    "ANC Visit, PNC Visit, Growth Monitoring",
                    "Monthly Visit, Quarterly Review",
                ],
                field_path="encounterTypes",
            ))

        # --- Forms with no fields ---
        for form in forms:
            form_name = form.get("name", "Unnamed Form")
            groups = form.get("groups", [])
            total_fields = sum(len(g.get("fields", [])) for g in groups)
            if total_fields == 0:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.INCOMPLETE_FORM,
                    severity=GapSeverity.CRITICAL,
                    question=f"Form '{form_name}' has no fields defined. What data should it collect?",
                    context=f"Form '{form_name}' exists but contains no field definitions.",
                    suggestions=[
                        "Basic demographics (name, age, gender, phone)",
                        "Health vitals (weight, height, BP, temperature)",
                        "Program-specific assessments",
                    ],
                    field_path=f"forms[name={form_name}].groups",
                ))

        # --- No registration form ---
        has_registration = any(
            f.get("formType") == "IndividualProfile"
            for f in forms
        )
        if not has_registration and forms:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.INCOMPLETE_FORM,
                severity=GapSeverity.IMPORTANT,
                question="No registration form is defined. Should one be created with standard fields (name, age, gender, address)?",
                context="A registration form (IndividualProfile) is typically required but none was found.",
                suggestions=["Yes, create with standard fields", "No, registration is handled elsewhere"],
                default="Yes, create with standard fields",
                field_path="forms",
            ))

        # --- Programs without enrolment forms ---
        for prog in programs:
            prog_name = prog.get("name", "") if isinstance(prog, dict) else str(prog)
            has_enrolment = any(
                f.get("formType") == "ProgramEnrolment" and f.get("programName") == prog_name
                for f in forms
            )
            if not has_enrolment:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.INCOMPLETE_FORM,
                    severity=GapSeverity.IMPORTANT,
                    question=f"Program '{prog_name}' has no enrolment form. Should one be created?",
                    context=f"Program '{prog_name}' needs a ProgramEnrolment form to capture enrolment data.",
                    suggestions=[
                        f"Yes, create enrolment form for {prog_name}",
                        "No, enrolment has no extra fields",
                    ],
                    default=f"Yes, create with standard fields",
                    field_path=f"forms",
                ))

        return questions

    def _check_concept_clarity(self, srs: dict) -> list[ClarityQuestion]:
        """Check for ambiguous or unclear concept definitions."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])

        # Collect all field names and their data types across all forms
        field_usage: dict[str, list[dict]] = defaultdict(list)  # name -> [{form, type, ...}]

        for form in forms:
            form_name = form.get("name", "Unnamed")
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    name = fld.get("name", "")
                    if not name:
                        continue
                    field_usage[name].append({
                        "form": form_name,
                        "dataType": fld.get("dataType", ""),
                        "options": fld.get("options"),
                        "type": fld.get("type"),
                    })

        # --- Same concept name with different data types ---
        for name, usages in field_usage.items():
            types_used = {u["dataType"] for u in usages if u["dataType"]}
            if len(types_used) > 1:
                forms_list = [u["form"] for u in usages]
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.CONFLICTING_INFO,
                    severity=GapSeverity.CRITICAL,
                    question=(
                        f"Field '{name}' has different data types in different forms: "
                        f"{', '.join(types_used)}. Which type should be used everywhere?"
                    ),
                    context=f"'{name}' appears in: {', '.join(forms_list)} with types {types_used}.",
                    suggestions=list(types_used),
                    field_path=f"concept:{name}",
                ))

        # --- Field with ambiguous or missing data type ---
        for form in forms:
            form_name = form.get("name", "Unnamed")
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    name = fld.get("name", "")
                    dtype = fld.get("dataType", "")

                    if not dtype or dtype not in _VALID_DATA_TYPES:
                        questions.append(ClarityQuestion(
                            id=_qid(),
                            category=GapCategory.AMBIGUOUS_CONCEPT,
                            severity=GapSeverity.IMPORTANT,
                            question=f"What data type should field '{name}' in form '{form_name}' use?",
                            context=f"Field '{name}' has data type '{dtype}' which is not a recognized Avni type.",
                            suggestions=["Text", "Numeric", "Coded", "Date", "Notes"],
                            default="Text",
                            field_path=f"forms[{form_name}].fields[{name}].dataType",
                        ))

        # --- Concept name collision detection (question names vs answer names) ---
        all_field_names: set[str] = set()
        all_answer_names: set[str] = set()

        for form in forms:
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    fname = fld.get("name", "").strip()
                    if fname:
                        all_field_names.add(fname)
                    for opt in (fld.get("options") or []):
                        if isinstance(opt, str) and opt.strip():
                            all_answer_names.add(opt.strip())

        collisions = all_field_names & all_answer_names
        for collision in collisions:
            # Find which forms use this as a field vs as an answer
            as_field_in = []
            as_answer_in = []
            for form in forms:
                for group in form.get("groups", []):
                    for fld in group.get("fields", []):
                        if fld.get("name", "").strip() == collision:
                            as_field_in.append(form.get("name", "?"))
                        if collision in (fld.get("options") or []):
                            as_answer_in.append(f"{form.get('name', '?')}/{fld.get('name', '?')}")

            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.CONFLICTING_INFO,
                severity=GapSeverity.CRITICAL,
                question=(
                    f"'{collision}' is used as both a field name and an answer option. "
                    f"Avni requires unique concept names. How should I rename one?"
                ),
                context=(
                    f"As field in: {', '.join(as_field_in[:3])}. "
                    f"As answer in: {', '.join(as_answer_in[:3])}."
                ),
                suggestions=[
                    f"Rename field to '{collision} Status'",
                    f"Rename field to '{collision} Present'",
                    f"Rename answer to '{collision} (option)'",
                ],
                field_path=f"concept:{collision}",
            ))

        # --- Known collision-risk concept names ---
        for form in forms:
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    fname = (fld.get("name") or "").strip().lower()
                    if fname in _COLLISION_RISK_NAMES:
                        # Only flag if also appears as an answer somewhere
                        if fld["name"] not in collisions:
                            # Check if it COULD appear as an answer in other forms
                            for other_form in forms:
                                for og in other_form.get("groups", []):
                                    for of in og.get("fields", []):
                                        opts = [o.lower() for o in (of.get("options") or [])]
                                        if fname in opts and fld["name"] not in collisions:
                                            collisions.add(fld["name"])  # mark as handled

        return questions

    def _check_rule_completeness(self, srs: dict) -> list[ClarityQuestion]:
        """Check for incomplete skip logic, decisions, or validation rules."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])

        for form in forms:
            form_name = form.get("name", "Unnamed")
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    name = fld.get("name", "")
                    kvs = fld.get("keyValues") or []

                    # Check for skip logic references
                    for kv in kvs:
                        key = kv.get("key", "")
                        value = str(kv.get("value", ""))

                        # Show/hide conditions that reference unknown fields
                        if key in ("ExcludedAnswers", "skipLogic", "showWhen", "hideWhen"):
                            # Check if referenced concept exists
                            if value and not self._field_exists_in_forms(value, forms):
                                questions.append(ClarityQuestion(
                                    id=_qid(),
                                    category=GapCategory.MISSING_RULE,
                                    severity=GapSeverity.IMPORTANT,
                                    question=(
                                        f"Skip logic on '{name}' in '{form_name}' references "
                                        f"'{value}' which doesn't appear to be a defined field. "
                                        f"What should it reference?"
                                    ),
                                    context=f"keyValue {key}={value} on field '{name}'.",
                                    suggestions=[],
                                    field_path=f"forms[{form_name}].fields[{name}].keyValues",
                                ))

                    # Check for numeric fields without validation ranges
                    if fld.get("dataType") == "Numeric":
                        has_range = (
                            fld.get("lowAbsolute") is not None
                            or fld.get("highAbsolute") is not None
                        )
                        if not has_range:
                            questions.append(ClarityQuestion(
                                id=_qid(),
                                category=GapCategory.MISSING_RULE,
                                severity=GapSeverity.NICE_TO_HAVE,
                                question=(
                                    f"Should numeric field '{name}' in '{form_name}' "
                                    f"have validation ranges (min/max values)?"
                                ),
                                context=f"Numeric field '{name}' has no absolute range limits defined.",
                                suggestions=["No validation needed", "Add standard ranges"],
                                default="No validation needed",
                                field_path=f"forms[{form_name}].fields[{name}]",
                            ))

        return questions

    def _check_visit_schedules(self, srs: dict) -> list[ClarityQuestion]:
        """Check for vague or missing visit schedule definitions."""
        questions: list[ClarityQuestion] = []
        schedules = srs.get("visitSchedules") or []
        programs = srs.get("programs", [])
        encounter_types = srs.get("encounterTypes", [])
        pem = srs.get("programEncounterMappings") or []

        # --- Programs with encounter types but no visit schedules ---
        if programs and (encounter_types or pem) and not schedules:
            questions.append(ClarityQuestion(
                id=_qid(),
                category=GapCategory.UNCLEAR_SCHEDULE,
                severity=GapSeverity.NICE_TO_HAVE,
                question=(
                    "No visit schedules are defined. Should visits be scheduled "
                    "automatically (e.g., ANC every 4 weeks)?"
                ),
                context=(
                    "Programs and encounter types exist but no visitSchedules "
                    "entries were found. Visits can still be created manually."
                ),
                suggestions=[
                    "No automatic scheduling needed",
                    "Yes, schedule visits automatically",
                ],
                default="No automatic scheduling needed",
                field_path="visitSchedules",
            ))

        # --- Check schedule entries for vagueness ---
        for i, sched in enumerate(schedules):
            sched_text = str(sched) if not isinstance(sched, dict) else str(sched)

            for pattern in _VAGUE_SCHEDULE_TERMS:
                if re.search(pattern, sched_text, re.IGNORECASE):
                    questions.append(ClarityQuestion(
                        id=_qid(),
                        category=GapCategory.UNCLEAR_SCHEDULE,
                        severity=GapSeverity.IMPORTANT,
                        question=f"Visit schedule entry is vague: '{sched_text[:100]}'. Can you specify the exact frequency?",
                        context=f"Schedule mentions a pattern but doesn't give specific timing (days/weeks/months).",
                        suggestions=[
                            "Every 4 weeks",
                            "Monthly (30 days)",
                            "Weekly",
                            "As needed (no schedule)",
                        ],
                        field_path=f"visitSchedules[{i}]",
                    ))
                    break  # one question per schedule entry

            # Check for schedule without encounter type reference
            if isinstance(sched, dict):
                if not sched.get("encounterType") and not sched.get("encounterTypeName"):
                    questions.append(ClarityQuestion(
                        id=_qid(),
                        category=GapCategory.UNCLEAR_SCHEDULE,
                        severity=GapSeverity.IMPORTANT,
                        question=f"Visit schedule does not specify which encounter type it applies to. Which one?",
                        context=f"Schedule: {sched_text[:100]}",
                        suggestions=encounter_types[:5] if encounter_types else [],
                        field_path=f"visitSchedules[{i}].encounterType",
                    ))

        return questions

    def _check_form_mappings(self, srs: dict) -> list[ClarityQuestion]:
        """Check for forms not properly mapped to entities."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])
        programs = srs.get("programs", [])
        encounter_types = srs.get("encounterTypes", [])

        for form in forms:
            form_name = form.get("name", "Unnamed")
            form_type = form.get("formType", "")

            # --- Invalid form type ---
            if form_type and form_type not in _VALID_FORM_TYPES:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.MISSING_MAPPING,
                    severity=GapSeverity.CRITICAL,
                    question=f"Form '{form_name}' has invalid formType '{form_type}'. What type should it be?",
                    context=f"Valid types: {', '.join(sorted(_VALID_FORM_TYPES))}.",
                    suggestions=sorted(_VALID_FORM_TYPES),
                    field_path=f"forms[name={form_name}].formType",
                ))

            # --- Program encounter forms without programName ---
            if form_type in ("ProgramEnrolment", "ProgramExit", "ProgramEncounter", "ProgramEncounterCancellation"):
                if not form.get("programName"):
                    prog_names = [
                        p.get("name", "?") for p in programs
                        if isinstance(p, dict) and "name" in p
                    ]
                    questions.append(ClarityQuestion(
                        id=_qid(),
                        category=GapCategory.MISSING_MAPPING,
                        severity=GapSeverity.CRITICAL,
                        question=f"Form '{form_name}' (type: {form_type}) is not linked to any program. Which program does it belong to?",
                        context=f"Program-related forms must specify programName.",
                        suggestions=prog_names[:5],
                        field_path=f"forms[name={form_name}].programName",
                    ))

            # --- Encounter forms without encounterTypeName ---
            if form_type in ("ProgramEncounter", "ProgramEncounterCancellation", "Encounter", "IndividualEncounterCancellation"):
                if not form.get("encounterTypeName"):
                    questions.append(ClarityQuestion(
                        id=_qid(),
                        category=GapCategory.MISSING_MAPPING,
                        severity=GapSeverity.CRITICAL,
                        question=f"Form '{form_name}' (type: {form_type}) has no encounter type assigned. Which encounter type does it capture?",
                        context=f"Encounter forms must specify encounterTypeName.",
                        suggestions=encounter_types[:5] if isinstance(encounter_types, list) else [],
                        field_path=f"forms[name={form_name}].encounterTypeName",
                    ))

            # --- No formType at all ---
            if not form_type:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.MISSING_MAPPING,
                    severity=GapSeverity.CRITICAL,
                    question=f"Form '{form_name}' has no formType. What kind of form is it?",
                    context="Every form must have a formType to determine how it maps to Avni's data model.",
                    suggestions=[
                        "IndividualProfile (registration)",
                        "ProgramEnrolment",
                        "ProgramEncounter (visit form)",
                        "Encounter (general visit)",
                    ],
                    field_path=f"forms[name={form_name}].formType",
                ))

        # --- Encounter types without any form ---
        all_form_ets = {f.get("encounterTypeName") for f in forms if f.get("encounterTypeName")}
        for et in (encounter_types if isinstance(encounter_types, list) else []):
            if et not in all_form_ets:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.MISSING_MAPPING,
                    severity=GapSeverity.IMPORTANT,
                    question=f"Encounter type '{et}' has no form assigned. Should a form be created for it?",
                    context=f"Encounter type '{et}' exists but no form captures data for it.",
                    suggestions=[f"Yes, create a form for '{et}'", "No, it's handled by another form"],
                    default=f"Yes, create a form for '{et}'",
                    field_path="forms",
                ))

        return questions

    def _check_answer_completeness(self, srs: dict) -> list[ClarityQuestion]:
        """Check for coded concepts missing answer options."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])

        for form in forms:
            form_name = form.get("name", "Unnamed")
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    name = fld.get("name", "")
                    dtype = fld.get("dataType", "")
                    options = fld.get("options") or []
                    selection_type = fld.get("type", "")

                    # --- Coded field with no options ---
                    if dtype == "Coded" and not options:
                        # Check if it's a yes/no-style field
                        name_lower = name.lower().strip()
                        is_yesno = any(
                            name_lower.startswith(ind) for ind in _YES_NO_FIELD_INDICATORS
                        ) or name_lower.endswith("?")

                        if is_yesno:
                            questions.append(ClarityQuestion(
                                id=_qid(),
                                category=GapCategory.MISSING_ANSWERS,
                                severity=GapSeverity.IMPORTANT,
                                question=f"Coded field '{name}' in '{form_name}' looks like a Yes/No question. Should it use standard Yes/No options?",
                                context=f"Field '{name}' is Coded with no options listed.",
                                suggestions=["Yes, use standard Yes/No", "No, it needs custom options: ..."],
                                default="Yes, use standard Yes/No",
                                field_path=f"forms[{form_name}].fields[{name}].options",
                            ))
                        else:
                            questions.append(ClarityQuestion(
                                id=_qid(),
                                category=GapCategory.MISSING_ANSWERS,
                                severity=GapSeverity.CRITICAL,
                                question=f"Coded field '{name}' in '{form_name}' has no answer options. What are the choices?",
                                context=f"Coded concepts must have at least one answer option defined.",
                                suggestions=[],
                                field_path=f"forms[{form_name}].fields[{name}].options",
                            ))

                    # --- Coded field with only 1 option (suspicious) ---
                    if dtype == "Coded" and len(options) == 1:
                        questions.append(ClarityQuestion(
                            id=_qid(),
                            category=GapCategory.MISSING_ANSWERS,
                            severity=GapSeverity.IMPORTANT,
                            question=f"Coded field '{name}' in '{form_name}' has only one option: '{options[0]}'. Are there more choices?",
                            context="A coded field with a single option is unusual. It might need more options or should be a different type.",
                            suggestions=[
                                f"Add more options",
                                "Change to Text type",
                                "This is correct, only one option needed",
                            ],
                            field_path=f"forms[{form_name}].fields[{name}].options",
                        ))

                    # --- Gender field with incomplete options ---
                    if name.lower().strip() in _GENDER_FIELD_NAMES and dtype == "Coded":
                        if options and len(options) == 2:
                            option_names = {o.lower() for o in options}
                            if option_names == {"male", "female"}:
                                questions.append(ClarityQuestion(
                                    id=_qid(),
                                    category=GapCategory.MISSING_ANSWERS,
                                    severity=GapSeverity.NICE_TO_HAVE,
                                    question=f"Gender field in '{form_name}' has only Male/Female. Should 'Other' or 'Transgender' be included?",
                                    context="Some implementations require additional gender options for inclusivity.",
                                    suggestions=["Male, Female, Other", "Male, Female, Transgender, Other", "Keep as Male, Female"],
                                    default="Keep as Male, Female",
                                    field_path=f"forms[{form_name}].fields[{name}].options",
                                ))

                    # --- Coded field with vague options ---
                    if dtype == "Coded" and options:
                        vague_options = [o for o in options if o.lower() in ("other", "others", "etc", "etc.", "...")]
                        if len(vague_options) == len(options):
                            questions.append(ClarityQuestion(
                                id=_qid(),
                                category=GapCategory.MISSING_ANSWERS,
                                severity=GapSeverity.CRITICAL,
                                question=f"Coded field '{name}' in '{form_name}' has only vague options ({', '.join(options)}). What are the actual choices?",
                                context="Options like 'Other', 'etc.' are not sufficient for a coded field.",
                                suggestions=[],
                                field_path=f"forms[{form_name}].fields[{name}].options",
                            ))

                    # --- MultiSelect vs SingleSelect not specified for Coded ---
                    if dtype == "Coded" and options and len(options) > 2:
                        if not selection_type or selection_type not in ("SingleSelect", "MultiSelect"):
                            questions.append(ClarityQuestion(
                                id=_qid(),
                                category=GapCategory.AMBIGUOUS_CONCEPT,
                                severity=GapSeverity.NICE_TO_HAVE,
                                question=f"Should '{name}' in '{form_name}' allow selecting multiple options or just one?",
                                context=f"Coded field with {len(options)} options but selection type (Single/Multi) is not specified.",
                                suggestions=["SingleSelect", "MultiSelect"],
                                default="SingleSelect",
                                field_path=f"forms[{form_name}].fields[{name}].type",
                            ))

        return questions

    def _check_conflicts(self, srs: dict) -> list[ClarityQuestion]:
        """Check for contradictory information in the SRS."""
        questions: list[ClarityQuestion] = []
        forms = srs.get("forms", [])
        programs = srs.get("programs", [])

        # --- Duplicate form names ---
        form_names = [f.get("name", "") for f in forms]
        name_counts = Counter(form_names)
        for name, count in name_counts.items():
            if count > 1 and name:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.CONFLICTING_INFO,
                    severity=GapSeverity.CRITICAL,
                    question=f"Form name '{name}' appears {count} times. Should these be merged or renamed?",
                    context="Avni requires unique form names.",
                    suggestions=[f"Merge into one form", f"Rename duplicates"],
                    field_path=f"forms[name={name}]",
                ))

        # --- Duplicate program names ---
        prog_names = [
            p.get("name", "") for p in programs
            if isinstance(p, dict) and "name" in p
        ]
        prog_counts = Counter(prog_names)
        for name, count in prog_counts.items():
            if count > 1 and name:
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.CONFLICTING_INFO,
                    severity=GapSeverity.CRITICAL,
                    question=f"Program '{name}' is defined {count} times. Should duplicates be removed?",
                    context="Programs must have unique names.",
                    suggestions=["Remove duplicates"],
                    field_path="programs",
                ))

        # --- Form with encounter type but wrong formType ---
        for form in forms:
            form_name = form.get("name", "")
            form_type = form.get("formType", "")
            has_program = bool(form.get("programName"))
            has_encounter = bool(form.get("encounterTypeName"))

            # Has programName but formType is not program-related
            if has_program and form_type in ("IndividualProfile", "Encounter", "IndividualEncounterCancellation"):
                questions.append(ClarityQuestion(
                    id=_qid(),
                    category=GapCategory.CONFLICTING_INFO,
                    severity=GapSeverity.IMPORTANT,
                    question=(
                        f"Form '{form_name}' has programName set but formType is '{form_type}' "
                        f"(not a program form type). Should formType be ProgramEncounter or ProgramEnrolment?"
                    ),
                    context="A form with programName should typically be ProgramEnrolment, ProgramExit, or ProgramEncounter.",
                    suggestions=["ProgramEncounter", "ProgramEnrolment", "ProgramExit"],
                    field_path=f"forms[name={form_name}].formType",
                ))

        return questions

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------

    def _field_exists_in_forms(self, field_ref: str, forms: list[dict]) -> bool:
        """Check if a field name exists anywhere in the forms."""
        for form in forms:
            for group in form.get("groups", []):
                for fld in group.get("fields", []):
                    if fld.get("name", "") == field_ref:
                        return True
        return False

    def _format_question(self, q: ClarityQuestion, number: int) -> str:
        """Format a single question for chat display."""
        parts = [f"{number}. {q.question}"]
        if q.suggestions:
            options_str = " / ".join(f"`{s}`" for s in q.suggestions[:4])
            parts.append(f"   Suggestions: {options_str}")
        if q.context and len(q.context) < 150:
            parts.append(f"   *({q.context})*")
        return "\n".join(parts)

    def _apply_single_answer(self, srs: dict, qid: str, answer: str) -> None:
        """Apply a single answer to the SRS data.

        This is a best-effort operation. Complex answers (like adding new forms)
        require LLM assistance and are handled separately in the chat flow.
        """
        # For now, store answers in a metadata section for the LLM to process
        if "_clarity_answers" not in srs:
            srs["_clarity_answers"] = {}
        srs["_clarity_answers"][qid] = answer

    async def _enrich_suggestions(
        self,
        questions: list[ClarityQuestion],
        srs: dict,
        org_context: dict | None,
    ) -> None:
        """Use RAG to add smart suggestions from similar org bundles.

        Best-effort: if RAG is unavailable, questions keep their static suggestions.
        """
        try:
            from app.services.rag.fallback import rag_service

            if not rag_service.is_rag_available:
                return

            # Build a sector/org query for context
            sector = (org_context or {}).get("sector", "")
            org_name = (org_context or {}).get("org_name", "")

            for q in questions:
                if q.suggestions:
                    # Already has suggestions, skip unless it's missing answers
                    if q.category != GapCategory.MISSING_ANSWERS:
                        continue

                # Search for similar concepts/patterns in org bundles
                search_query = q.question[:100]
                if sector:
                    search_query = f"{sector} {search_query}"

                try:
                    results = await rag_service.search(
                        query=search_query,
                        collection="concepts",
                        top_k=3,
                    )
                    if results:
                        rag_suggestions = []
                        for r in results:
                            # Extract answer options from similar concepts
                            text = r.text[:200]
                            if "answers" in text.lower() or "options" in text.lower():
                                rag_suggestions.append(f"Similar: {text[:80]}")

                        if rag_suggestions:
                            q.suggestions.extend(rag_suggestions[:2])
                except Exception:
                    pass  # RAG search for individual question failed, continue

        except ImportError:
            logger.debug("RAG service not available for suggestion enrichment")
        except Exception as e:
            logger.debug("RAG suggestion enrichment failed: %s", e)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

clarity_engine = ClarityEngine()
