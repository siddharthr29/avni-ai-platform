"""Unified Pre-Flight Bundle Validator.

6-layer validation that mirrors Avni server contracts exactly.
Consolidates checks from:
  - bundle_generator.validate_bundle()
  - bundle_validator.BundleValidator
  - srs-bundle-generator/validators/server_validation.js

Goal: catch 100% of server rejection reasons BEFORE upload.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import uuid as uuid_mod
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "PreFlightValidator",
    "ValidationResult",
    "ValidationError",
    "ValidationWarning",
    "AutoFix",
    "Severity",
    "validate_bundle",
    "fix_and_validate_bundle",
]

# ---------------------------------------------------------------------------
# Constants — superset of all three validators, aligned to avni-server source
# ---------------------------------------------------------------------------

VALID_DATA_TYPES = {
    "NA", "Numeric", "Text", "Coded", "Date", "DateTime", "Time",
    "QuestionGroup", "Location", "Duration", "Image", "ImageV2",
    "File", "Audio", "Video", "PhoneNumber", "Subject", "Id",
    "GroupAffiliation", "Notes", "Encounter", "Boolean",
}

VALID_FORM_TYPES = {
    "IndividualProfile", "ProgramEnrolment", "ProgramExit",
    "ProgramEncounter", "ProgramEncounterCancellation",
    "Encounter", "IndividualEncounterCancellation",
    "ChecklistItem", "Location", "Task",
}

VALID_SUBJECT_TYPES = {"Person", "Individual", "Household", "Group", "User"}

VALID_FORM_ELEMENT_TYPES = {"SingleSelect", "MultiSelect"}

# From avni-server ValidationUtil.java
NAME_INVALID_CHARS = re.compile(r'[<>="]')
COMMON_INVALID_CHARS = re.compile(r"""[<>="']""")

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# Required top-level files for a valid bundle
REQUIRED_FILES = [
    "subjectTypes.json",
    "operationalSubjectTypes.json",
    "concepts.json",
    "formMappings.json",
]

# Valid files/dirs allowed in a bundle
ALLOWED_TOPLEVEL = {
    "subjectTypes.json", "operationalSubjectTypes.json",
    "concepts.json", "formMappings.json",
    "programs.json", "operationalPrograms.json",
    "encounterTypes.json", "operationalEncounterTypes.json",
    "groupPrivilege.json", "groups.json",
    "organisationConfig.json", "addressLevelTypes.json",
    "locations.json", "catchments.json",
    "identifierSource.json", "relationshipType.json",
    "individualRelation.json", "individualRelationGenderMapping.json",
    "checklistDetail.json", "taskType.json", "taskStatus.json",
    "forms", "rules",
}

# Correct dependency order for upload (server processes in this order)
UPLOAD_ORDER = [
    "organisationConfig.json",
    "addressLevelTypes.json",
    "locations.json",
    "catchments.json",
    "concepts.json",
    "subjectTypes.json",
    "operationalSubjectTypes.json",
    "programs.json",
    "operationalPrograms.json",
    "encounterTypes.json",
    "operationalEncounterTypes.json",
    "forms",
    "formMappings.json",
    "identifierSource.json",
    "relationshipType.json",
    "individualRelation.json",
    "individualRelationGenderMapping.json",
    "checklistDetail.json",
    "taskType.json",
    "taskStatus.json",
    "groups.json",
    "groupPrivilege.json",
]

# Security-forbidden patterns in rule code
RULE_FORBIDDEN_PATTERNS = [
    (re.compile(r"\beval\s*\("), "eval() is forbidden"),
    (re.compile(r"\bFunction\s*\("), "Function() constructor is forbidden"),
    (re.compile(r"\brequire\s*\("), "require() is not available in Avni rule engine"),
    (re.compile(r"\bimport\s+"), "ES module imports are not supported"),
    (re.compile(r"\bfetch\s*\("), "fetch() is not available (offline-first)"),
    (re.compile(r"\bprocess\."), "process object is not available"),
]

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB per file

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    layer: int
    category: str
    message: str
    file: str = ""
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": "error",
            "layer": self.layer,
            "category": self.category,
            "message": self.message,
            "file": self.file,
            "fix_hint": self.fix_hint,
        }


@dataclass
class ValidationWarning:
    layer: int
    category: str
    message: str
    file: str = ""
    fix_hint: str = ""

    def to_dict(self) -> dict:
        return {
            "severity": "warning",
            "layer": self.layer,
            "category": self.category,
            "message": self.message,
            "file": self.file,
            "fix_hint": self.fix_hint,
        }


@dataclass
class AutoFix:
    category: str
    description: str
    file: str
    original: Any = None
    fixed: Any = None
    applied: bool = False

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "description": self.description,
            "file": self.file,
            "applied": self.applied,
        }


@dataclass
class ValidationResult:
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
    auto_fixes: list[AutoFix] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def summary(self) -> str:
        lines = []
        if self.errors:
            lines.append(f"{len(self.errors)} error(s):")
            for e in self.errors:
                lines.append(f"  [L{e.layer}] ERROR: {e.message}")
        if self.warnings:
            lines.append(f"{len(self.warnings)} warning(s):")
            for w in self.warnings:
                lines.append(f"  [L{w.layer}] WARN: {w.message}")
        if self.auto_fixes:
            applied = [f for f in self.auto_fixes if f.applied]
            lines.append(f"{len(self.auto_fixes)} auto-fix(es) available ({len(applied)} applied)")
        if not lines:
            lines.append("Pre-flight validation passed — no issues found.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        all_issues = [e.to_dict() for e in self.errors] + [w.to_dict() for w in self.warnings]
        return {
            "valid": self.is_valid,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "auto_fix_count": len(self.auto_fixes),
            # Combined issues list (backward-compatible with old BundleValidator)
            "issues": all_issues,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "auto_fixes": [f.to_dict() for f in self.auto_fixes],
        }


# ---------------------------------------------------------------------------
# PreFlightValidator
# ---------------------------------------------------------------------------


class PreFlightValidator:
    """6-layer bundle validation that mirrors Avni server contracts exactly.

    Layers:
        1. Schema Validation — files exist, valid JSON, required fields, enums
        2. Reference Integrity — cross-file UUID references, answer concepts
        3. Collision Detection — duplicate names, UUIDs, display orders
        4. Business Rules — numeric ranges, form-type matching, invalid chars
        5. Rule Validation — JS syntax, declarative rule schema, concept refs
        6. Zip Structure — dependency order, extraneous files, size limits
    """

    def __init__(self) -> None:
        self.result = ValidationResult()
        # Loaded data caches
        self._bundle_dir: str = ""
        self._concepts: dict[str, dict] = {}  # uuid -> concept
        self._concept_names: dict[str, str] = {}  # lowercase name -> uuid
        self._forms: dict[str, dict] = {}  # uuid -> form data
        self._form_names: dict[str, str] = {}  # name -> uuid
        self._subject_types: dict[str, dict] = {}  # uuid -> subject type
        self._programs: dict[str, dict] = {}  # uuid -> program
        self._encounter_types: dict[str, dict] = {}  # uuid -> encounter type
        self._form_mappings: list[dict] = []
        self._group_privileges: list[dict] = []
        self._all_uuids: dict[str, str] = {}  # uuid -> "source:name" for global dedup

    def validate(self, bundle_path: str | Path) -> ValidationResult:
        """Run all 6 layers. Returns errors, warnings, and auto-fixes."""
        self.result = ValidationResult()
        bundle_path = str(bundle_path)

        # Resolve bundle directory (handles zip or dir)
        bundle_dir = self._resolve_bundle_dir(bundle_path)
        if bundle_dir is None:
            return self.result
        self._bundle_dir = bundle_dir

        # Load all data first
        self._load_all(bundle_dir)

        # Run all 6 layers
        self._layer1_schema(bundle_dir)
        self._layer2_references()
        self._layer3_collisions()
        self._layer4_business_rules()
        self._layer5_rule_validation(bundle_dir)
        self._layer6_zip_structure(bundle_dir)

        return self.result

    def fix_and_revalidate(self, bundle_path: str | Path) -> ValidationResult:
        """Apply auto-fixes then re-run validation.

        1. Run initial validation to discover fixable issues
        2. Apply all auto-fixes to the bundle files on disk
        3. Re-run validation to confirm fixes worked
        """
        bundle_path = str(bundle_path)

        # Initial validation
        self.validate(bundle_path)

        bundle_dir = self._resolve_bundle_dir(bundle_path)
        if bundle_dir is None:
            return self.result

        if not self.result.auto_fixes:
            return self.result

        # Apply fixes
        fixes_applied = self._apply_auto_fixes(bundle_dir)

        if fixes_applied > 0:
            logger.info("Applied %d auto-fix(es), re-validating...", fixes_applied)
            # Re-run full validation
            self.__init__()  # Reset state
            self.validate(bundle_path)

        return self.result

    # -----------------------------------------------------------------------
    # Bundle loading
    # -----------------------------------------------------------------------

    def _resolve_bundle_dir(self, bundle_path: str) -> str | None:
        """Resolve a zip or directory path to a bundle directory."""
        if os.path.isdir(bundle_path):
            return bundle_path

        if bundle_path.endswith(".zip") and os.path.isfile(bundle_path):
            import tempfile
            tmp_dir = tempfile.mkdtemp(prefix="preflight_")
            try:
                with zipfile.ZipFile(bundle_path, "r") as zf:
                    zf.extractall(tmp_dir)
            except zipfile.BadZipFile as e:
                self.result.errors.append(ValidationError(
                    6, "bad_zip", f"Cannot open zip file: {e}", bundle_path,
                ))
                return None
            entries = [e for e in os.listdir(tmp_dir) if e != "__MACOSX"]
            if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
                return os.path.join(tmp_dir, entries[0])
            return tmp_dir

        self.result.errors.append(ValidationError(
            6, "not_found", f"Bundle path does not exist: {bundle_path}", bundle_path,
        ))
        return None

    def _read_json(self, bundle_dir: str, filename: str) -> Any | None:
        """Read and parse a JSON file from the bundle."""
        filepath = os.path.join(bundle_dir, filename)
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            self.result.errors.append(ValidationError(
                1, "invalid_json", f"Invalid JSON in {filename}: {e}", filename,
            ))
            return None

    def _load_all(self, bundle_dir: str) -> None:
        """Load all JSON files into memory for cross-referencing."""
        # Concepts
        concepts_data = self._read_json(bundle_dir, "concepts.json")
        if isinstance(concepts_data, list):
            for c in concepts_data:
                uid = c.get("uuid", "")
                name = c.get("name", "")
                if uid:
                    self._concepts[uid] = c
                    self._all_uuids[uid] = f"concepts:{name}"
                if name:
                    self._concept_names[name.lower().strip()] = uid

        # Subject types
        st_data = self._read_json(bundle_dir, "subjectTypes.json")
        if isinstance(st_data, list):
            for st in st_data:
                uid = st.get("uuid", "")
                if uid:
                    self._subject_types[uid] = st
                    self._all_uuids[uid] = f"subjectTypes:{st.get('name', '')}"

        # Programs
        prog_data = self._read_json(bundle_dir, "programs.json")
        if isinstance(prog_data, list):
            for p in prog_data:
                uid = p.get("uuid", "")
                if uid:
                    self._programs[uid] = p
                    self._all_uuids[uid] = f"programs:{p.get('name', '')}"

        # Encounter types
        et_data = self._read_json(bundle_dir, "encounterTypes.json")
        if isinstance(et_data, list):
            for et in et_data:
                uid = et.get("uuid", "")
                if uid:
                    self._encounter_types[uid] = et
                    self._all_uuids[uid] = f"encounterTypes:{et.get('name', '')}"

        # Form mappings
        fm_data = self._read_json(bundle_dir, "formMappings.json")
        if isinstance(fm_data, list):
            self._form_mappings = fm_data

        # Group privileges
        gp_data = self._read_json(bundle_dir, "groupPrivilege.json")
        if isinstance(gp_data, list):
            self._group_privileges = gp_data

        # Forms
        forms_dir = os.path.join(bundle_dir, "forms")
        if os.path.isdir(forms_dir):
            for fname in sorted(os.listdir(forms_dir)):
                if not fname.endswith(".json"):
                    continue
                form_data = self._read_json(bundle_dir, f"forms/{fname}")
                if isinstance(form_data, dict):
                    uid = form_data.get("uuid", "")
                    name = form_data.get("name", "")
                    if uid:
                        self._forms[uid] = form_data
                        self._all_uuids[uid] = f"forms:{name}"
                    if name:
                        self._form_names[name] = uid

    # -----------------------------------------------------------------------
    # LAYER 1: Schema Validation
    # -----------------------------------------------------------------------

    def _layer1_schema(self, bundle_dir: str) -> None:
        """Validate file existence, JSON parsing, required fields, UUIDs, enums."""
        L = 1

        # 1a. Required files exist
        for rf in REQUIRED_FILES:
            if not os.path.isfile(os.path.join(bundle_dir, rf)):
                self.result.errors.append(ValidationError(
                    L, "missing_file", f"Missing required file: {rf}", rf,
                ))

        # 1b. Validate concepts schema
        for uid, c in self._concepts.items():
            name = c.get("name", "")
            dt = c.get("dataType", "")
            ctx = f"Concept '{name}'"

            # Required fields
            if not name:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"Concept with UUID '{uid}' missing 'name'",
                    "concepts.json",
                ))
            if not uid:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"Concept '{name}' missing 'uuid'",
                    "concepts.json",
                ))
                self.result.auto_fixes.append(AutoFix(
                    "missing_uuid",
                    f"Generate UUID for concept '{name}'",
                    "concepts.json",
                    original=None,
                    fixed=str(uuid_mod.uuid4()),
                ))
            if not dt:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'dataType'",
                    "concepts.json",
                ))

            # UUID format
            if uid and not UUID_PATTERN.match(uid):
                self.result.errors.append(ValidationError(
                    L, "invalid_uuid", f"{ctx} has invalid UUID: '{uid}'",
                    "concepts.json",
                ))

            # Valid enum
            if dt and dt not in VALID_DATA_TYPES:
                self.result.errors.append(ValidationError(
                    L, "invalid_enum",
                    f"{ctx} has invalid dataType: '{dt}' (valid: {sorted(VALID_DATA_TYPES)})",
                    "concepts.json",
                ))

            # Empty string for required fields
            if name is not None and isinstance(name, str) and name.strip() == "" and name != "":
                self.result.errors.append(ValidationError(
                    L, "empty_field", f"Concept has whitespace-only name", "concepts.json",
                ))

        # 1c. Validate subject types schema
        for uid, st in self._subject_types.items():
            name = st.get("name", "")
            ctx = f"SubjectType '{name}'"
            if not name:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'name'", "subjectTypes.json",
                ))
            if not uid:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'uuid'", "subjectTypes.json",
                ))
            st_type = st.get("type", "")
            if st_type and st_type not in VALID_SUBJECT_TYPES:
                self.result.warnings.append(ValidationWarning(
                    L, "unusual_type", f"{ctx} has unusual type: '{st_type}'",
                    "subjectTypes.json",
                ))

        # 1d. Validate programs schema
        for uid, prog in self._programs.items():
            name = prog.get("name", "")
            ctx = f"Program '{name}'"
            if not name:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'name'", "programs.json",
                ))
            if not uid:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'uuid'", "programs.json",
                ))
            if not prog.get("colour"):
                self.result.warnings.append(ValidationWarning(
                    L, "missing_colour", f"{ctx} missing 'colour'", "programs.json",
                ))

        # 1e. Validate encounter types schema
        for uid, et in self._encounter_types.items():
            name = et.get("name", "")
            ctx = f"EncounterType '{name}'"
            if not name:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'name'", "encounterTypes.json",
                ))
            if not uid:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'uuid'", "encounterTypes.json",
                ))

        # 1f. Validate forms schema
        for uid, form in self._forms.items():
            name = form.get("name", "")
            ctx = f"Form '{name}'"
            if not name:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'name'", f"forms/",
                ))
            if not uid:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'uuid'", f"forms/",
                ))
            ft = form.get("formType", "")
            if not ft:
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'formType'", f"forms/",
                ))
            if ft and ft not in VALID_FORM_TYPES:
                self.result.errors.append(ValidationError(
                    L, "invalid_enum", f"{ctx} has invalid formType: '{ft}'", f"forms/",
                ))

            # Validate form element types
            for feg in form.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    fe_type = fe.get("type", "")
                    if fe_type and fe_type not in VALID_FORM_ELEMENT_TYPES:
                        self.result.warnings.append(ValidationWarning(
                            L, "unusual_type",
                            f"{ctx}, element '{fe.get('name', '')}' has unusual type: '{fe_type}'",
                            f"forms/",
                        ))

        # 1g. Validate form mappings schema
        for i, fm in enumerate(self._form_mappings):
            ctx = f"FormMapping {i + 1} ('{fm.get('formName', '')}')"
            if not fm.get("formUUID"):
                self.result.errors.append(ValidationError(
                    L, "missing_field", f"{ctx} missing 'formUUID'",
                    "formMappings.json",
                ))
            fm_type = fm.get("formType", "")
            if fm_type and fm_type not in VALID_FORM_TYPES:
                self.result.errors.append(ValidationError(
                    L, "invalid_enum", f"{ctx} has invalid formType: '{fm_type}'",
                    "formMappings.json",
                ))

    # -----------------------------------------------------------------------
    # LAYER 2: Reference Integrity
    # -----------------------------------------------------------------------

    def _layer2_references(self) -> None:
        """Validate cross-file UUID references."""
        L = 2

        # 2a. Form elements reference existing concept UUIDs
        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)
            for feg in form.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    if fe.get("voided"):
                        continue
                    concept = fe.get("concept", {})
                    concept_uuid = concept.get("uuid", "")
                    concept_name = concept.get("name", "?")
                    if concept_name and concept_name.startswith("PLACEHOLDER_"):
                        continue
                    if concept_uuid and concept_uuid not in self._concepts:
                        self.result.errors.append(ValidationError(
                            L, "missing_concept",
                            f"Form '{form_name}', element '{fe.get('name', '')}': "
                            f"concept UUID '{concept_uuid}' (name: '{concept_name}') "
                            f"not found in concepts.json",
                            f"forms/{form_name}.json",
                            "Add the concept to concepts.json or fix the UUID",
                        ))

        # 2b. Form mappings reference existing form UUIDs
        for fm in self._form_mappings:
            fm_name = fm.get("formName", "?")
            form_uuid = fm.get("formUUID", "")
            if form_uuid and form_uuid not in self._forms:
                self.result.errors.append(ValidationError(
                    L, "orphaned_mapping",
                    f"FormMapping '{fm_name}' references unknown form UUID '{form_uuid}'",
                    "formMappings.json",
                    "Ensure the form JSON file exists in forms/ directory",
                ))

            # 2c. Form mappings reference existing program UUIDs
            prog_uuid = fm.get("programUUID", "")
            if prog_uuid and prog_uuid not in self._programs:
                self.result.errors.append(ValidationError(
                    L, "missing_program",
                    f"FormMapping '{fm_name}' references unknown program UUID '{prog_uuid}'",
                    "formMappings.json",
                ))

            # 2d. Form mappings reference existing encounterType UUIDs
            et_uuid = fm.get("encounterTypeUUID", "")
            if et_uuid and et_uuid not in self._encounter_types:
                self.result.errors.append(ValidationError(
                    L, "missing_encounter_type",
                    f"FormMapping '{fm_name}' references unknown encounterType UUID '{et_uuid}'",
                    "formMappings.json",
                ))

            # 2e. Form mappings reference existing subjectType UUIDs
            st_uuid = fm.get("subjectTypeUUID", "")
            if st_uuid and st_uuid not in self._subject_types:
                self.result.warnings.append(ValidationWarning(
                    L, "missing_subject_type",
                    f"FormMapping '{fm_name}' references unknown subjectType UUID '{st_uuid}'",
                    "formMappings.json",
                ))

        # 2f. Answer concepts reference existing concept UUIDs and have dataType NA
        for uid, c in self._concepts.items():
            if c.get("dataType") != "Coded":
                continue
            name = c.get("name", "")
            answers = c.get("answers", [])

            # 2g. Coded concepts should have at least one answer
            if not answers:
                self.result.warnings.append(ValidationWarning(
                    L, "no_answers",
                    f"Coded concept '{name}' has no answers defined",
                    "concepts.json",
                ))
                continue

            for ans in answers:
                ans_uuid = ans.get("uuid", "")
                ans_name = ans.get("name", "")

                # Answer must have name or uuid
                if not ans_uuid and not ans_name:
                    self.result.errors.append(ValidationError(
                        L, "answer_missing_id",
                        f"Coded concept '{name}' has answer without name or uuid",
                        "concepts.json",
                    ))
                    continue

                # Answer concept must exist in concepts.json
                if ans_uuid and ans_uuid not in self._concepts:
                    self.result.errors.append(ValidationError(
                        L, "answer_uuid_mismatch",
                        f"Coded concept '{name}' has answer '{ans_name}' "
                        f"with UUID '{ans_uuid}' not found as NA concept in concepts.json",
                        "concepts.json",
                        "Ensure all answer options are defined as NA-type concepts",
                    ))

        # 2h. Subject type sync concept references
        for uid, st in self._subject_types.items():
            st_name = st.get("name", "")
            for field_name in ("syncRegistrationConcept1", "syncRegistrationConcept2"):
                ref = st.get(field_name)
                if ref and ref not in self._concepts:
                    self.result.warnings.append(ValidationWarning(
                        L, "missing_sync_concept",
                        f"SubjectType '{st_name}': {field_name} UUID not found in concepts",
                        "subjectTypes.json",
                    ))

    # -----------------------------------------------------------------------
    # LAYER 3: Collision Detection
    # -----------------------------------------------------------------------

    def _layer3_collisions(self) -> None:
        """Detect duplicate names, UUIDs, and display orders."""
        L = 3

        # 3a. Duplicate concept names (case-insensitive)
        seen_names: dict[str, str] = {}  # lowercase -> first uuid
        for uid, c in self._concepts.items():
            name = c.get("name", "").lower().strip()
            if not name:
                continue
            if name in seen_names and seen_names[name] != uid:
                self.result.errors.append(ValidationError(
                    L, "duplicate_concept_name",
                    f"Duplicate concept name (case-insensitive): '{c.get('name')}' "
                    f"(UUIDs: {seen_names[name]}, {uid})",
                    "concepts.json",
                    "Remove or rename one of the duplicates",
                ))
                # Auto-fix: append program prefix (if we can determine one)
                self.result.auto_fixes.append(AutoFix(
                    "concept_name_collision",
                    f"Rename duplicate concept '{c.get('name')}' to avoid collision",
                    "concepts.json",
                    original=c.get("name"),
                    fixed=None,  # Will be resolved during apply
                ))
            else:
                seen_names[name] = uid

        # 3b. Duplicate UUIDs across ANY file
        uuid_sources: dict[str, list[str]] = {}
        for uid, source in self._all_uuids.items():
            uuid_sources.setdefault(uid, []).append(source)
        for uid, sources in uuid_sources.items():
            if len(sources) > 1:
                self.result.errors.append(ValidationError(
                    L, "duplicate_uuid",
                    f"Duplicate UUID '{uid}' found in: {', '.join(sources)}",
                    "",
                ))

        # 3c. Duplicate form names
        seen_form_names: dict[str, str] = {}
        for uid, form in self._forms.items():
            name = form.get("name", "").lower().strip()
            if not name:
                continue
            if name in seen_form_names:
                self.result.errors.append(ValidationError(
                    L, "duplicate_form_name",
                    f"Duplicate form name: '{form.get('name')}'",
                    "forms/",
                ))
            else:
                seen_form_names[name] = uid

        # 3d. Duplicate program names
        seen_prog_names: set[str] = set()
        for uid, prog in self._programs.items():
            name = prog.get("name", "").lower().strip()
            if name and name in seen_prog_names:
                self.result.errors.append(ValidationError(
                    L, "duplicate_program_name",
                    f"Duplicate program name: '{prog.get('name')}'",
                    "programs.json",
                ))
            if name:
                seen_prog_names.add(name)

        # 3e. Duplicate encounter type names
        seen_et_names: set[str] = set()
        for uid, et in self._encounter_types.items():
            name = et.get("name", "").lower().strip()
            if name and name in seen_et_names:
                self.result.errors.append(ValidationError(
                    L, "duplicate_encounter_type_name",
                    f"Duplicate encounter type name: '{et.get('name')}'",
                    "encounterTypes.json",
                ))
            if name:
                seen_et_names.add(name)

        # 3f. Duplicate display orders within a form element group
        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)
            for feg in form.get("formElementGroups", []):
                group_name = feg.get("name", "")
                display_orders: dict[float, str] = {}
                for fe in feg.get("formElements", []):
                    d_order = fe.get("displayOrder")
                    fe_name = fe.get("name", "")
                    if d_order is not None:
                        if d_order in display_orders:
                            self.result.errors.append(ValidationError(
                                L, "duplicate_display_order",
                                f"Form '{form_name}', group '{group_name}': "
                                f"duplicate displayOrder {d_order} "
                                f"(elements: '{display_orders[d_order]}', '{fe_name}')",
                                f"forms/",
                            ))
                            self.result.auto_fixes.append(AutoFix(
                                "duplicate_display_order",
                                f"Renumber displayOrder in form '{form_name}', group '{group_name}'",
                                f"forms/{form_name}.json",
                            ))
                        else:
                            display_orders[d_order] = fe_name

        # 3g. Duplicate concept within same form
        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)
            used_concepts: set[str] = set()
            for feg in form.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    if fe.get("voided"):
                        continue
                    if fe.get("parentFormElementUuid"):
                        continue  # Skip child elements (QuestionGroup)
                    concept_uuid = fe.get("concept", {}).get("uuid", "")
                    concept_name = fe.get("concept", {}).get("name", "")
                    if concept_uuid and concept_uuid in used_concepts:
                        self.result.errors.append(ValidationError(
                            L, "duplicate_concept_in_form",
                            f"Form '{form_name}': concept '{concept_name}' "
                            f"({concept_uuid}) appears multiple times",
                            f"forms/",
                        ))
                    if concept_uuid:
                        used_concepts.add(concept_uuid)

        # 3h. Duplicate answer orders within a coded concept
        for uid, c in self._concepts.items():
            if c.get("dataType") != "Coded":
                continue
            name = c.get("name", "")
            answer_orders: set[Any] = set()
            for ans in c.get("answers", []):
                a_order = ans.get("order")
                if a_order is not None and a_order in answer_orders:
                    self.result.warnings.append(ValidationWarning(
                        L, "duplicate_answer_order",
                        f"Concept '{name}' has duplicate answer order: {a_order}",
                        "concepts.json",
                    ))
                if a_order is not None:
                    answer_orders.add(a_order)

        # 3i. Duplicate group privileges
        seen_privs: set[tuple] = set()
        for gp in self._group_privileges:
            key = (
                gp.get("groupUUID", ""),
                gp.get("privilegeType", ""),
                gp.get("subjectTypeUUID", ""),
                gp.get("programUUID", ""),
                gp.get("encounterTypeUUID", ""),
            )
            if key in seen_privs:
                self.result.warnings.append(ValidationWarning(
                    L, "duplicate_privilege",
                    f"Duplicate groupPrivilege: {gp.get('privilegeType')} "
                    f"for group {gp.get('groupUUID', '')[:8]}",
                    "groupPrivilege.json",
                    "Remove the duplicate entry",
                ))
            seen_privs.add(key)

    # -----------------------------------------------------------------------
    # LAYER 4: Business Rules
    # -----------------------------------------------------------------------

    def _layer4_business_rules(self) -> None:
        """Validate business logic constraints."""
        L = 4

        # 4a. Numeric concepts: range validation
        for uid, c in self._concepts.items():
            if c.get("dataType") != "Numeric":
                continue
            name = c.get("name", "")
            low_abs = c.get("lowAbsolute")
            high_abs = c.get("highAbsolute")
            low_norm = c.get("lowNormal")
            high_norm = c.get("highNormal")

            if low_abs is not None and high_abs is not None:
                if low_abs >= high_abs:
                    self.result.errors.append(ValidationError(
                        L, "invalid_range",
                        f"Concept '{name}': lowAbsolute ({low_abs}) must be < highAbsolute ({high_abs})",
                        "concepts.json",
                    ))
            if low_norm is not None and high_norm is not None:
                if low_norm >= high_norm:
                    self.result.errors.append(ValidationError(
                        L, "invalid_range",
                        f"Concept '{name}': lowNormal ({low_norm}) must be < highNormal ({high_norm})",
                        "concepts.json",
                    ))
            # Cross-range: lowAbsolute <= lowNormal <= highNormal <= highAbsolute
            if all(v is not None for v in [low_abs, low_norm]):
                if low_abs > low_norm:
                    self.result.warnings.append(ValidationWarning(
                        L, "range_order",
                        f"Concept '{name}': lowAbsolute ({low_abs}) > lowNormal ({low_norm})",
                        "concepts.json",
                    ))
            if all(v is not None for v in [high_norm, high_abs]):
                if high_norm > high_abs:
                    self.result.warnings.append(ValidationWarning(
                        L, "range_order",
                        f"Concept '{name}': highNormal ({high_norm}) > highAbsolute ({high_abs})",
                        "concepts.json",
                    ))

        # 4b. Invalid characters in names (from avni-server ValidationUtil.java)
        for uid, c in self._concepts.items():
            name = c.get("name", "")
            if name and NAME_INVALID_CHARS.search(name):
                self.result.errors.append(ValidationError(
                    L, "invalid_chars",
                    f"Concept '{name}' contains invalid characters (<, >, =, \")",
                    "concepts.json",
                ))
                sanitized = NAME_INVALID_CHARS.sub("", name).strip()
                if sanitized:
                    self.result.auto_fixes.append(AutoFix(
                        "invalid_chars",
                        f"Sanitize concept name '{name}' -> '{sanitized}'",
                        "concepts.json",
                        original=name,
                        fixed=sanitized,
                    ))

        for uid, st in self._subject_types.items():
            name = st.get("name", "")
            if name and NAME_INVALID_CHARS.search(name):
                self.result.errors.append(ValidationError(
                    L, "invalid_chars",
                    f"SubjectType '{name}' contains invalid characters",
                    "subjectTypes.json",
                ))

        for uid, prog in self._programs.items():
            name = prog.get("name", "")
            if name and NAME_INVALID_CHARS.search(name):
                self.result.errors.append(ValidationError(
                    L, "invalid_chars",
                    f"Program '{name}' contains invalid characters",
                    "programs.json",
                ))

        for uid, et in self._encounter_types.items():
            name = et.get("name", "")
            if name and NAME_INVALID_CHARS.search(name):
                self.result.errors.append(ValidationError(
                    L, "invalid_chars",
                    f"EncounterType '{name}' contains invalid characters",
                    "encounterTypes.json",
                ))

        # 4c. Form type matches entity type in form mappings
        for fm in self._form_mappings:
            form_uuid = fm.get("formUUID", "")
            form = self._forms.get(form_uuid)
            if not form:
                continue
            form_type = form.get("formType", "")
            fm_name = fm.get("formName", "?")

            # ProgramEnrolment/ProgramExit must have programUUID
            if form_type in ("ProgramEnrolment", "ProgramExit"):
                if not fm.get("programUUID"):
                    self.result.warnings.append(ValidationWarning(
                        L, "missing_program_ref",
                        f"FormMapping '{fm_name}': {form_type} form should have programUUID",
                        "formMappings.json",
                    ))

            # ProgramEncounter/ProgramEncounterCancellation must have encounterTypeUUID
            if form_type in ("ProgramEncounter", "ProgramEncounterCancellation"):
                if not fm.get("encounterTypeUUID"):
                    self.result.warnings.append(ValidationWarning(
                        L, "missing_et_ref",
                        f"FormMapping '{fm_name}': {form_type} form should have encounterTypeUUID",
                        "formMappings.json",
                    ))

            # Cannot associate Registration form with User subject type
            if form_type == "IndividualProfile" and fm.get("subjectTypeUUID"):
                st = self._subject_types.get(fm["subjectTypeUUID"])
                if st and st.get("type") == "User":
                    self.result.errors.append(ValidationError(
                        L, "user_registration",
                        f"FormMapping '{fm_name}': Cannot associate Registration form with User subject type",
                        "formMappings.json",
                    ))

                # Check if form name contains a different subject type name than what's mapped
                if st:
                    mapped_st_name = st.get("name", "").lower()
                    form_name_lower = fm_name.lower()
                    for st_uuid_check, st_data in self._subject_types.items():
                        st_name_check = st_data.get("name", "").lower()
                        if (st_name_check in form_name_lower
                                and st_name_check != mapped_st_name
                                and st_uuid_check != fm.get("subjectTypeUUID")):
                            self.result.errors.append(ValidationError(
                                L, "mismatched_subject_type",
                                f"FormMapping '{fm_name}': form name suggests subject type "
                                f"'{st_data['name']}' but is mapped to '{st['name']}'. "
                                f"This will cause the form to appear under the wrong subject type.",
                                "formMappings.json",
                            ))

        # 4d. Scheduled encounters have cancellation forms
        program_encounter_ets: set[str] = set()
        cancellation_ets: set[str] = set()
        for fm in self._form_mappings:
            ft = fm.get("formType", "")
            et_uuid = fm.get("encounterTypeUUID", "")
            if ft == "ProgramEncounter" and et_uuid:
                program_encounter_ets.add(et_uuid)
            elif ft == "ProgramEncounterCancellation" and et_uuid:
                cancellation_ets.add(et_uuid)

        missing_cancellation = program_encounter_ets - cancellation_ets
        for et_uuid in missing_cancellation:
            et = self._encounter_types.get(et_uuid, {})
            et_name = et.get("name", et_uuid)
            self.result.warnings.append(ValidationWarning(
                L, "missing_cancellation",
                f"No cancellation form found for scheduled encounter type '{et_name}'",
                "formMappings.json",
                f"Create a ProgramEncounterCancellation form and mapping for '{et_name}'",
            ))
            self.result.auto_fixes.append(AutoFix(
                "missing_cancellation_form",
                f"Generate cancellation form for encounter type '{et_name}'",
                "formMappings.json",
                original=et_uuid,
            ))

        # 4e. Encounter types have matching form mappings
        mapped_ets = {fm.get("encounterTypeUUID") for fm in self._form_mappings if fm.get("encounterTypeUUID")}
        for uid, et in self._encounter_types.items():
            if uid not in mapped_ets:
                self.result.warnings.append(ValidationWarning(
                    L, "unmapped_encounter_type",
                    f"EncounterType '{et.get('name', '')}' has no form mapping",
                    "encounterTypes.json",
                ))

        # 4f. Display order is sequential and positive
        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)
            for feg in form.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    d_order = fe.get("displayOrder")
                    if d_order is not None and (not isinstance(d_order, (int, float)) or d_order <= 0):
                        self.result.warnings.append(ValidationWarning(
                            L, "invalid_display_order",
                            f"Form '{form_name}': displayOrder {d_order} should be positive",
                            f"forms/",
                        ))

    # -----------------------------------------------------------------------
    # LAYER 5: Rule Validation
    # -----------------------------------------------------------------------

    def _layer5_rule_validation(self, bundle_dir: str) -> None:
        """Validate JavaScript and declarative rules."""
        L = 5

        # 5a. Form-level rules
        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)

            for rule_field in ("decisionRule", "visitScheduleRule", "validationRule", "editFormRule"):
                rule_code = form.get(rule_field, "")
                if rule_code and isinstance(rule_code, str) and rule_code.strip():
                    issues = self._validate_js_rule(rule_code, rule_field)
                    for issue in issues:
                        self.result.errors.append(ValidationError(
                            L, "invalid_rule",
                            f"Form '{form_name}': {rule_field} - {issue}",
                            f"forms/",
                        ))

            # 5b. Form element rules
            for feg in form.get("formElementGroups", []):
                for fe in feg.get("formElements", []):
                    fe_name = fe.get("name", "")

                    # JavaScript rule
                    rule_code = fe.get("rule", "")
                    if rule_code and isinstance(rule_code, str) and rule_code.strip():
                        issues = self._validate_js_rule(rule_code, "ViewFilter")
                        for issue in issues:
                            self.result.warnings.append(ValidationWarning(
                                L, "invalid_element_rule",
                                f"Form '{form_name}' > '{fe_name}': {issue}",
                                f"forms/",
                            ))

                    # Declarative rule
                    decl_rule = fe.get("declarativeRule")
                    if decl_rule and isinstance(decl_rule, list) and len(decl_rule) > 0:
                        issues = self._validate_declarative_rule(decl_rule[0])
                        for issue in issues:
                            self.result.warnings.append(ValidationWarning(
                                L, "invalid_declarative_rule",
                                f"Form '{form_name}' > '{fe_name}': {issue}",
                                f"forms/",
                            ))

        # 5c. Entity-level rules
        for uid, st in self._subject_types.items():
            st_name = st.get("name", "")
            for rule_field in ("subjectSummaryRule", "programEligibilityCheckRule"):
                rule_code = st.get(rule_field, "")
                if rule_code and isinstance(rule_code, str) and rule_code.strip():
                    issues = self._validate_js_rule(rule_code, rule_field)
                    for issue in issues:
                        self.result.errors.append(ValidationError(
                            L, "invalid_rule",
                            f"SubjectType '{st_name}': {rule_field} - {issue}",
                            "subjectTypes.json",
                        ))

        for uid, prog in self._programs.items():
            prog_name = prog.get("name", "")
            for rule_field in ("enrolmentSummaryRule", "enrolmentEligibilityCheckRule"):
                rule_code = prog.get(rule_field, "")
                if rule_code and isinstance(rule_code, str) and rule_code.strip():
                    issues = self._validate_js_rule(rule_code, rule_field)
                    for issue in issues:
                        self.result.errors.append(ValidationError(
                            L, "invalid_rule",
                            f"Program '{prog_name}': {rule_field} - {issue}",
                            "programs.json",
                        ))

        for uid, et in self._encounter_types.items():
            et_name = et.get("name", "")
            rule_code = et.get("entityEligibilityCheckRule", "")
            if rule_code and isinstance(rule_code, str) and rule_code.strip():
                issues = self._validate_js_rule(rule_code, "Eligibility")
                for issue in issues:
                    self.result.errors.append(ValidationError(
                        L, "invalid_rule",
                        f"EncounterType '{et_name}': entityEligibilityCheckRule - {issue}",
                        "encounterTypes.json",
                    ))

        # 5d. Standalone rule files in rules/ directory
        rules_dir = os.path.join(bundle_dir, "rules")
        if os.path.isdir(rules_dir):
            for fname in sorted(os.listdir(rules_dir)):
                if not fname.endswith(".js"):
                    continue
                fpath = os.path.join(rules_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        code = f.read()
                    issues = self._validate_js_rule(code, "standalone")
                    for issue in issues:
                        self.result.warnings.append(ValidationWarning(
                            L, "invalid_rule_file",
                            f"Rule file '{fname}': {issue}",
                            f"rules/{fname}",
                        ))
                except Exception as e:
                    self.result.errors.append(ValidationError(
                        L, "rule_read_error",
                        f"Cannot read rule file '{fname}': {e}",
                        f"rules/{fname}",
                    ))

    def _validate_js_rule(self, code: str, rule_type: str) -> list[str]:
        """Validate JavaScript rule syntax and security. Returns list of issue messages."""
        issues: list[str] = []
        if not code or not code.strip():
            return issues

        # Check balanced delimiters
        if not self._check_balanced_delimiters(code):
            issues.append("Unbalanced braces/brackets/parentheses")

        # Check forbidden patterns (security)
        for pattern, msg in RULE_FORBIDDEN_PATTERNS:
            if pattern.search(code):
                issues.append(msg)

        # Check concept references exist (UUIDs in rule code)
        uuid_refs = re.findall(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            code, re.IGNORECASE,
        )
        for ref_uuid in uuid_refs:
            if ref_uuid not in self._concepts and ref_uuid not in self._all_uuids:
                issues.append(f"Rule references unknown UUID '{ref_uuid}'")

        return issues

    def _validate_declarative_rule(self, rule: Any) -> list[str]:
        """Validate a declarative rule JSON structure."""
        issues: list[str] = []
        if not isinstance(rule, dict):
            issues.append("Declarative rule must be a JSON object")
            return issues

        valid_scopes = {
            "registration", "enrolment", "encounter", "entireEnrolment",
            "latestInAllEncounters", "latestInPreviousEncounters",
            "latestInEntireEnrolment", "lastEncounter", "exit",
            "cancelEncounter", "checklistItem",
        }

        valid_actions = {
            "showFormElement", "hideFormElement", "showFormElementGroup",
            "hideFormElementGroup", "value", "skipAnswers",
            "validationError", "showProgram", "hideProgram",
            "showEncounterType", "hideEncounterType",
            "formValidationError", "addDecision", "scheduleVisit",
        }

        # Check conditions
        conditions = rule.get("conditions", [])
        if isinstance(conditions, list):
            for cond in conditions:
                if isinstance(cond, dict):
                    scope = cond.get("scope", "")
                    if scope and scope not in valid_scopes:
                        issues.append(f"Invalid condition scope: '{scope}'")

        # Check actions
        actions = rule.get("actions", [])
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    action_type = action.get("type", "")
                    if action_type and action_type not in valid_actions:
                        issues.append(f"Invalid action type: '{action_type}'")

        return issues

    @staticmethod
    def _check_balanced_delimiters(code: str) -> bool:
        """Check braces, brackets, parentheses are balanced."""
        stack: list[str] = []
        pairs = {")": "(", "]": "[", "}": "{"}
        openers = set(pairs.values())
        in_string = False
        string_char: str | None = None
        escaped = False
        in_line_comment = False
        in_block_comment = False

        for i, ch in enumerate(code):
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if in_line_comment:
                if ch == "\n":
                    in_line_comment = False
                continue
            if in_block_comment:
                if ch == "*" and i + 1 < len(code) and code[i + 1] == "/":
                    in_block_comment = False
                continue
            if in_string:
                if ch == string_char:
                    in_string = False
                continue
            if ch in ("'", '"', "`"):
                in_string = True
                string_char = ch
                continue
            if ch == "/" and i + 1 < len(code):
                if code[i + 1] == "/":
                    in_line_comment = True
                    continue
                if code[i + 1] == "*":
                    in_block_comment = True
                    continue
            if ch in openers:
                stack.append(ch)
            elif ch in pairs:
                if not stack or stack[-1] != pairs[ch]:
                    return False
                stack.pop()

        return len(stack) == 0

    # -----------------------------------------------------------------------
    # LAYER 6: Zip Structure
    # -----------------------------------------------------------------------

    def _layer6_zip_structure(self, bundle_dir: str) -> None:
        """Validate zip structure, file ordering, extraneous files, sizes."""
        L = 6

        # 6a. Check for extraneous files
        try:
            for item in os.listdir(bundle_dir):
                if item.startswith(".") or item == "__MACOSX":
                    continue
                if item not in ALLOWED_TOPLEVEL:
                    self.result.warnings.append(ValidationWarning(
                        L, "extraneous_file",
                        f"Unexpected file/directory in bundle: '{item}'",
                        item,
                    ))
        except OSError:
            pass

        # 6b. Check file sizes
        for root, dirs, files in os.walk(bundle_dir):
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    size = os.path.getsize(fpath)
                    if size > MAX_FILE_SIZE_BYTES:
                        rel = os.path.relpath(fpath, bundle_dir)
                        self.result.errors.append(ValidationError(
                            L, "file_too_large",
                            f"File '{rel}' is {size / (1024*1024):.1f} MB "
                            f"(max: {MAX_FILE_SIZE_BYTES / (1024*1024):.0f} MB)",
                            rel,
                        ))
                except OSError:
                    pass

        # 6c. Correct directory structure (forms must be in forms/ subdir)
        forms_dir = os.path.join(bundle_dir, "forms")
        if os.path.isdir(forms_dir):
            for fname in os.listdir(forms_dir):
                if not fname.endswith(".json"):
                    self.result.warnings.append(ValidationWarning(
                        L, "non_json_in_forms",
                        f"Non-JSON file in forms/ directory: '{fname}'",
                        f"forms/{fname}",
                    ))

        # 6d. Verify files are in correct dependency order
        # (This checks that the bundle COULD be uploaded in order —
        #  it's an info check, not an error, since the server handles ordering)
        present_files = []
        for item in UPLOAD_ORDER:
            path = os.path.join(bundle_dir, item)
            if os.path.exists(path):
                present_files.append(item)

        # Check for files that exist but aren't in our known order
        try:
            actual_files = set(os.listdir(bundle_dir))
            actual_files.discard("__MACOSX")
            actual_files -= {f for f in actual_files if f.startswith(".")}
            known_files = set(UPLOAD_ORDER) | ALLOWED_TOPLEVEL
            unknown = actual_files - known_files
            for uf in unknown:
                self.result.warnings.append(ValidationWarning(
                    L, "unknown_file",
                    f"File '{uf}' is not in the known Avni bundle schema",
                    uf,
                ))
        except OSError:
            pass

    # -----------------------------------------------------------------------
    # Auto-fix application
    # -----------------------------------------------------------------------

    def _apply_auto_fixes(self, bundle_dir: str) -> int:
        """Apply auto-fixes to bundle files on disk. Returns count of fixes applied."""
        applied = 0

        for fix in self.result.auto_fixes:
            try:
                if fix.category == "concept_name_collision":
                    if self._fix_concept_name_collision(bundle_dir, fix):
                        fix.applied = True
                        applied += 1

                elif fix.category == "missing_uuid":
                    if self._fix_missing_uuid(bundle_dir, fix):
                        fix.applied = True
                        applied += 1

                elif fix.category == "duplicate_display_order":
                    if self._fix_duplicate_display_order(bundle_dir, fix):
                        fix.applied = True
                        applied += 1

                elif fix.category == "invalid_chars":
                    if self._fix_invalid_chars(bundle_dir, fix):
                        fix.applied = True
                        applied += 1

                elif fix.category == "missing_cancellation_form":
                    if self._fix_missing_cancellation_form(bundle_dir, fix):
                        fix.applied = True
                        applied += 1

            except Exception as e:
                logger.warning("Auto-fix failed for %s: %s", fix.category, e)

        return applied

    def _fix_concept_name_collision(self, bundle_dir: str, fix: AutoFix) -> bool:
        """Rename a duplicate concept by appending a suffix."""
        concepts_path = os.path.join(bundle_dir, "concepts.json")
        if not os.path.isfile(concepts_path):
            return False

        with open(concepts_path, "r", encoding="utf-8") as f:
            concepts = json.load(f)

        original_name = fix.original
        if not original_name:
            return False

        # Find the SECOND occurrence and rename it
        found_first = False
        modified = False
        for c in concepts:
            if c.get("name", "").lower().strip() == original_name.lower().strip():
                if not found_first:
                    found_first = True
                    continue
                # Determine a program prefix from form mappings if possible
                suffix = f" ({c.get('uuid', '')[:8]})"
                new_name = f"{c['name']}{suffix}"
                c["name"] = new_name
                fix.fixed = new_name
                modified = True
                break

        if modified:
            with open(concepts_path, "w", encoding="utf-8") as f:
                json.dump(concepts, f, indent=2, ensure_ascii=False)
            # Also update any form references to this concept
            self._update_concept_name_in_forms(bundle_dir, original_name, fix.fixed)
            return True
        return False

    def _fix_missing_uuid(self, bundle_dir: str, fix: AutoFix) -> bool:
        """Add a generated UUID to a concept missing one."""
        concepts_path = os.path.join(bundle_dir, "concepts.json")
        if not os.path.isfile(concepts_path):
            return False

        with open(concepts_path, "r", encoding="utf-8") as f:
            concepts = json.load(f)

        modified = False
        for c in concepts:
            if not c.get("uuid"):
                c["uuid"] = str(uuid_mod.uuid4())
                modified = True

        if modified:
            with open(concepts_path, "w", encoding="utf-8") as f:
                json.dump(concepts, f, indent=2, ensure_ascii=False)
            return True
        return False

    def _fix_duplicate_display_order(self, bundle_dir: str, fix: AutoFix) -> bool:
        """Renumber display orders sequentially within the affected form."""
        form_path = os.path.join(bundle_dir, fix.file)
        if not os.path.isfile(form_path):
            return False

        with open(form_path, "r", encoding="utf-8") as f:
            form = json.load(f)

        modified = False
        for feg in form.get("formElementGroups", []):
            elements = feg.get("formElements", [])
            orders = [fe.get("displayOrder", 0) for fe in elements]
            if len(orders) != len(set(orders)):  # Has duplicates
                for idx, fe in enumerate(elements, 1):
                    fe["displayOrder"] = idx
                modified = True

        if modified:
            with open(form_path, "w", encoding="utf-8") as f:
                json.dump(form, f, indent=2, ensure_ascii=False)
            return True
        return False

    def _fix_invalid_chars(self, bundle_dir: str, fix: AutoFix) -> bool:
        """Remove invalid characters from concept names."""
        concepts_path = os.path.join(bundle_dir, "concepts.json")
        if not os.path.isfile(concepts_path):
            return False

        with open(concepts_path, "r", encoding="utf-8") as f:
            concepts = json.load(f)

        modified = False
        for c in concepts:
            if c.get("name") == fix.original and fix.fixed:
                c["name"] = fix.fixed
                modified = True
                break

        if modified:
            with open(concepts_path, "w", encoding="utf-8") as f:
                json.dump(concepts, f, indent=2, ensure_ascii=False)
            self._update_concept_name_in_forms(bundle_dir, fix.original, fix.fixed)
            return True
        return False

    def _fix_missing_cancellation_form(self, bundle_dir: str, fix: AutoFix) -> bool:
        """Generate a minimal cancellation form and mapping for a scheduled encounter type."""
        et_uuid = fix.original
        if not et_uuid:
            return False

        et = self._encounter_types.get(et_uuid, {})
        et_name = et.get("name", "Unknown")

        # Generate cancellation form
        cancel_form_uuid = str(uuid_mod.uuid4())
        cancel_form = {
            "name": f"{et_name} Cancellation",
            "uuid": cancel_form_uuid,
            "formType": "ProgramEncounterCancellation",
            "formElementGroups": [
                {
                    "name": "Cancellation Details",
                    "uuid": str(uuid_mod.uuid4()),
                    "displayOrder": 1.0,
                    "formElements": [],
                }
            ],
        }

        # Write the form file
        forms_dir = os.path.join(bundle_dir, "forms")
        os.makedirs(forms_dir, exist_ok=True)
        form_filename = f"{et_name} Cancellation.json".replace(" ", "_")
        form_path = os.path.join(forms_dir, form_filename)
        with open(form_path, "w", encoding="utf-8") as f:
            json.dump(cancel_form, f, indent=2, ensure_ascii=False)

        # Add form mapping
        mappings_path = os.path.join(bundle_dir, "formMappings.json")
        mappings = []
        if os.path.isfile(mappings_path):
            with open(mappings_path, "r", encoding="utf-8") as f:
                mappings = json.load(f)

        # Find the corresponding ProgramEncounter mapping to get subjectType/program
        ref_mapping = None
        for fm in mappings:
            if fm.get("encounterTypeUUID") == et_uuid and fm.get("formType") == "ProgramEncounter":
                ref_mapping = fm
                break

        new_mapping = {
            "uuid": str(uuid_mod.uuid4()),
            "formUUID": cancel_form_uuid,
            "formName": f"{et_name} Cancellation",
            "formType": "ProgramEncounterCancellation",
            "subjectTypeUUID": ref_mapping.get("subjectTypeUUID", "") if ref_mapping else "",
            "programUUID": ref_mapping.get("programUUID", "") if ref_mapping else "",
            "encounterTypeUUID": et_uuid,
            "voided": False,
        }
        mappings.append(new_mapping)

        with open(mappings_path, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2, ensure_ascii=False)

        return True

    def _update_concept_name_in_forms(
        self, bundle_dir: str, old_name: str, new_name: str
    ) -> None:
        """Update concept name references in form files."""
        forms_dir = os.path.join(bundle_dir, "forms")
        if not os.path.isdir(forms_dir):
            return
        for fname in os.listdir(forms_dir):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(forms_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    form = json.load(f)
                modified = False
                for feg in form.get("formElementGroups", []):
                    for fe in feg.get("formElements", []):
                        concept = fe.get("concept", {})
                        if concept.get("name") == old_name:
                            concept["name"] = new_name
                            modified = True
                if modified:
                    with open(fpath, "w", encoding="utf-8") as f:
                        json.dump(form, f, indent=2, ensure_ascii=False)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Convenience function (drop-in replacement for old validate_bundle)
# ---------------------------------------------------------------------------


def validate_bundle(bundle_path: str) -> dict:
    """Convenience function — drop-in replacement for BundleValidator.validate_bundle().

    Returns dict with: valid, error_count, warning_count, auto_fix_count, errors, warnings, auto_fixes.
    """
    validator = PreFlightValidator()
    result = validator.validate(bundle_path)
    return result.to_dict()


def fix_and_validate_bundle(bundle_path: str) -> dict:
    """Apply auto-fixes then validate. Returns same format as validate_bundle."""
    validator = PreFlightValidator()
    result = validator.fix_and_revalidate(bundle_path)
    return result.to_dict()
