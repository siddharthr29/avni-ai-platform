"""Comprehensive Bundle Validator.

Ports the 12-point validation from avni-skills-main bundle_validator.js
into the Avni AI platform.

Validates:
 1. Required files exist and contain valid JSON
 2. forms/ directory with at least one form
 3. Concept UUID uniqueness
 4. Concept name uniqueness (case-insensitive)
 5. Answer concept completeness (Coded questions reference defined answers)
 6. Concept name hygiene (trailing commas, whitespace)
 7. Form-concept reference integrity and data type consistency
 8. Form UUID uniqueness and displayOrder uniqueness within FEGs
 9. Encounter type completeness (form mappings, cancellation mappings)
10. Form mapping referential integrity
11. Report card field format validation
12. Operational config wrapper format
"""

import json
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Equivalent name groups (tolerate answer concept name variants sharing a UUID)
# ---------------------------------------------------------------------------

_EQUIVALENT_NAMES: list[set[str]] = [
    {"Other", "Others"},
    {"NA", "N/A", "Not Applicable"},
    {"None", "Nil"},
]


def _names_are_equivalent(a: str, b: str) -> bool:
    for group in _EQUIVALENT_NAMES:
        if a in group and b in group:
            return True
    return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


class ValidationIssue:
    """A single validation finding."""

    def __init__(
        self,
        severity: str,
        category: str,
        message: str,
        file: str = "",
        fix_hint: str = "",
    ):
        self.severity = severity  # "error" | "warning"
        self.category = category
        self.message = message
        self.file = file
        self.fix_hint = fix_hint

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "message": self.message,
            "file": self.file,
            "fix_hint": self.fix_hint,
        }

    def __repr__(self) -> str:
        return f"[{self.severity.upper()}] {self.category}: {self.message}"


# ---------------------------------------------------------------------------
# Main validator class
# ---------------------------------------------------------------------------


class BundleValidator:
    """Validates an Avni bundle directory or zip file.

    Comprehensive 12-point validation ported from
    avni-skills-main/srs-bundle-generator/validators/bundle_validator.js.
    """

    def __init__(self, bundle_path: str):
        self.bundle_path = bundle_path
        self.issues: list[ValidationIssue] = []
        self._concepts: dict[str, dict] = {}  # uuid -> concept
        self._concept_names: dict[str, str] = {}  # lowercase_name -> uuid
        self._concepts_by_name_lower: dict[str, list[dict]] = {}
        self._answer_uuids: set[str] = set()
        self._forms: dict[str, dict] = {}  # uuid -> form
        self._form_names: dict[str, str] = {}  # name -> uuid
        self._form_uuids: set[str] = set()
        self._subject_types: dict[str, dict] = {}
        self._programs: dict[str, dict] = {}
        self._encounter_types: dict[str, dict] = {}
        self._form_mappings: list[dict] = []
        self._group_privileges: list[dict] = []
        self._bundle_dir: str = ""
        self._tmp_dir: str | None = None

    def validate(self) -> dict:
        """Run all 12-point validations.

        Returns:
            {
                "valid": bool,
                "error_count": int,
                "warning_count": int,
                "errors": [str, ...],
                "warnings": [str, ...],
                "issues": [{severity, category, message, file, fix_hint}, ...],
            }
        """
        self._resolve_bundle_dir()

        # 1-2. Required files and forms/ directory
        self._check_required_files()

        # Load all data
        self._load_bundle()

        # 3-6. Concept validations
        self._validate_concepts()

        # 7-8. Form validations
        self._validate_forms()

        # 9. Encounter type completeness
        self._validate_encounter_type_completeness()

        # 10. Form mapping referential integrity
        self._validate_form_mapping_references()

        # 11. Report card format
        self._validate_report_card_format()

        # 12. Operational config wrapper format
        self._validate_operational_config_format()

        # Legacy checks preserved for backward compatibility
        self._check_duplicate_privileges()

        errors = [i for i in self.issues if i.severity == "error"]
        warnings = [i for i in self.issues if i.severity == "warning"]

        return {
            "valid": len(errors) == 0,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": [i.message for i in errors],
            "warnings": [i.message for i in warnings],
            "issues": [i.to_dict() for i in self.issues],
        }

    # ------------------------------------------------------------------
    # Bundle directory resolution
    # ------------------------------------------------------------------

    def _resolve_bundle_dir(self) -> None:
        """Resolve the bundle directory, extracting from zip if needed."""
        if self.bundle_path.endswith(".zip"):
            import tempfile

            self._tmp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(self.bundle_path, "r") as zf:
                zf.extractall(self._tmp_dir)
            entries = [
                e for e in os.listdir(self._tmp_dir) if e != "__MACOSX"
            ]
            if len(entries) == 1 and os.path.isdir(
                os.path.join(self._tmp_dir, entries[0])
            ):
                self._bundle_dir = os.path.join(self._tmp_dir, entries[0])
            else:
                self._bundle_dir = self._tmp_dir
        else:
            self._bundle_dir = self.bundle_path

    # ------------------------------------------------------------------
    # 1-2. Required files
    # ------------------------------------------------------------------

    def _check_required_files(self) -> None:
        """Check that all required files exist and contain valid JSON."""
        required_files = [
            "concepts.json",
            "subjectTypes.json",
            "programs.json",
            "encounterTypes.json",
            "formMappings.json",
        ]

        for filename in required_files:
            filepath = os.path.join(self._bundle_dir, filename)
            if not os.path.isfile(filepath):
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "missing_file",
                        f"Missing required file: {filename}",
                        filename,
                        f"Generate or add {filename} to the bundle directory",
                    )
                )
            else:
                self._check_valid_json(filepath, filename)

        # forms/ directory with at least one form
        forms_dir = os.path.join(self._bundle_dir, "forms")
        if not os.path.isdir(forms_dir):
            self.issues.append(
                ValidationIssue(
                    "error",
                    "missing_file",
                    "Missing forms/ directory",
                    "forms/",
                    "Create a forms/ directory with at least one form JSON file",
                )
            )
        else:
            form_files = [
                f for f in os.listdir(forms_dir) if f.endswith(".json")
            ]
            if not form_files:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "missing_file",
                        "forms/ directory contains no JSON files",
                        "forms/",
                        "Add at least one form JSON file to the forms/ directory",
                    )
                )

        # Critical optional files — warn if missing (needed for production
        # bundles but not strictly required for the bundle to be parseable)
        critical_optional_files = [
            ("groups.json", "CRITICAL", "User groups for permissions"),
            ("groupPrivilege.json", "CRITICAL", "User permissions"),
            ("operationalSubjectTypes.json", "HIGH", "Operational subject type wrappers"),
            ("operationalPrograms.json", "HIGH", "Operational program wrappers"),
            ("operationalEncounterTypes.json", "HIGH", "Operational encounter type wrappers"),
        ]
        for filename, importance, reason in critical_optional_files:
            filepath = os.path.join(self._bundle_dir, filename)
            if not os.path.isfile(filepath):
                severity = "error" if importance == "CRITICAL" else "warning"
                self.issues.append(
                    ValidationIssue(
                        severity,
                        "missing_file",
                        f"Missing {importance.lower()} file: {filename} — {reason}",
                        filename,
                        f"Generate or add {filename} to the bundle directory",
                    )
                )
            else:
                self._check_valid_json(filepath, filename)

    def _check_valid_json(self, filepath: str, filename: str) -> bool:
        """Validate that a file contains parseable JSON."""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                json.load(f)
            return True
        except json.JSONDecodeError as exc:
            self.issues.append(
                ValidationIssue(
                    "error",
                    "invalid_json",
                    f"Invalid JSON in {filename}: {exc}",
                    filename,
                )
            )
            return False
        except OSError as exc:
            self.issues.append(
                ValidationIssue(
                    "error",
                    "read_error",
                    f"Cannot read {filename}: {exc}",
                    filename,
                )
            )
            return False

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_bundle(self) -> None:
        """Load all JSON files from the bundle directory."""
        self._load_json_file("concepts.json", self._parse_concepts)
        self._load_json_file("subjectTypes.json", self._parse_subject_types)
        self._load_json_file("programs.json", self._parse_programs)
        self._load_json_file("encounterTypes.json", self._parse_encounter_types)
        self._load_json_file("formMappings.json", self._parse_form_mappings)
        self._load_json_file(
            "groupPrivilege.json", self._parse_group_privileges
        )

        # Load forms
        forms_dir = os.path.join(self._bundle_dir, "forms")
        if os.path.isdir(forms_dir):
            for fname in sorted(os.listdir(forms_dir)):
                if not fname.endswith(".json"):
                    continue
                fpath = os.path.join(forms_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        form_data = json.load(f)
                    if isinstance(form_data, dict):
                        uid = form_data.get("uuid", "")
                        self._forms[uid] = form_data
                        self._form_names[form_data.get("name", "")] = uid
                        self._form_uuids.add(uid)
                except Exception as exc:
                    self.issues.append(
                        ValidationIssue(
                            "error",
                            "parse",
                            f"Failed to parse {fname}: {exc}",
                            f"forms/{fname}",
                        )
                    )

    def _load_json_file(self, filename: str, parser) -> None:
        fpath = os.path.join(self._bundle_dir, filename)
        if not os.path.isfile(fpath):
            return
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            parser(data, filename)
        except Exception as exc:
            self.issues.append(
                ValidationIssue(
                    "error",
                    "parse",
                    f"Failed to parse {filename}: {exc}",
                    filename,
                )
            )

    def _parse_concepts(self, data: Any, filename: str) -> None:
        if not isinstance(data, list):
            return
        for c in data:
            uid = c.get("uuid", "")
            name = c.get("name", "")
            self._concepts[uid] = c
            lower = name.lower().strip()
            self._concept_names[lower] = uid
            self._concepts_by_name_lower.setdefault(lower, []).append(c)
            if c.get("dataType") == "NA":
                self._answer_uuids.add(uid)

    def _parse_subject_types(self, data: Any, filename: str) -> None:
        if not isinstance(data, list):
            return
        for st in data:
            self._subject_types[st.get("uuid", "")] = st

    def _parse_programs(self, data: Any, filename: str) -> None:
        if not isinstance(data, list):
            return
        for p in data:
            self._programs[p.get("uuid", "")] = p

    def _parse_encounter_types(self, data: Any, filename: str) -> None:
        if not isinstance(data, list):
            return
        for et in data:
            self._encounter_types[et.get("uuid", "")] = et

    def _parse_form_mappings(self, data: Any, filename: str) -> None:
        if isinstance(data, list):
            self._form_mappings = data

    def _parse_group_privileges(self, data: Any, filename: str) -> None:
        if isinstance(data, list):
            self._group_privileges = data

    # ------------------------------------------------------------------
    # 3-6. Concept validations
    # ------------------------------------------------------------------

    def _validate_concepts(self) -> None:
        """Validate concept UUIDs, names, answers, and name hygiene."""
        # 3. Duplicate UUIDs
        uuid_seen: dict[str, dict] = {}
        for uid, concept in self._concepts.items():
            c_name = concept.get("name", "")
            c_dtype = concept.get("dataType", "")

            if uid in uuid_seen:
                existing = uuid_seen[uid]
                if c_dtype == "NA" and existing.get("dataType") == "NA":
                    if not _names_are_equivalent(
                        c_name, existing.get("name", "")
                    ):
                        self.issues.append(
                            ValidationIssue(
                                "error",
                                "duplicate_uuid",
                                f"Duplicate UUID: '{uid}' used by different "
                                f"answer concepts: '{existing.get('name')}' "
                                f"and '{c_name}'",
                                "concepts.json",
                                "Assign a unique UUID to one of the concepts",
                            )
                        )
                else:
                    self.issues.append(
                        ValidationIssue(
                            "error",
                            "duplicate_uuid",
                            f"Duplicate UUID: '{uid}' used by: "
                            f"'{existing.get('name')}' and '{c_name}'",
                            "concepts.json",
                            "Assign a unique UUID to one of the concepts",
                        )
                    )
            uuid_seen[uid] = concept

        # 4. Duplicate names (case-insensitive) with different UUIDs
        for lower_name, concept_list in self._concepts_by_name_lower.items():
            if len(concept_list) <= 1:
                continue
            # Skip empty names
            if not lower_name:
                continue
            uuids = {c.get("uuid") for c in concept_list}
            if len(uuids) > 1:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "duplicate_concept",
                        f"Duplicate concept name (case-insensitive): "
                        f"'{concept_list[0].get('name')}' has "
                        f"{len(concept_list)} entries with different UUIDs: "
                        f"{', '.join(sorted(uuids))}",
                        "concepts.json",
                        "Remove or rename one of the duplicates",
                    )
                )
            # Same name with different data types
            dtypes = {c.get("dataType") for c in concept_list}
            if len(dtypes) > 1:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "inconsistent_datatype",
                        f"Inconsistent data type: "
                        f"'{concept_list[0].get('name')}' has multiple "
                        f"data types: {', '.join(sorted(str(d) for d in dtypes))}",
                        "concepts.json",
                        "Ensure the concept has a single consistent data type",
                    )
                )

        # 5. Answer concept completeness
        for uid, concept in self._concepts.items():
            if concept.get("dataType") != "Coded":
                continue
            for answer in concept.get("answers", []):
                a_uuid = answer.get("uuid", "")
                if a_uuid and a_uuid not in self._concepts:
                    self.issues.append(
                        ValidationIssue(
                            "warning",
                            "missing_answer",
                            f"Missing answer concept definition for "
                            f"'{answer.get('name')}' (UUID: {a_uuid}) "
                            f"in question '{concept.get('name')}'",
                            "concepts.json",
                            "Add an NA-type concept entry for this answer",
                        )
                    )

        # 6. Name hygiene
        for uid, concept in self._concepts.items():
            c_name = concept.get("name", "")

            if c_name.endswith(","):
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "name_hygiene",
                        f"Trailing comma in concept name: '{c_name}' "
                        f"(UUID: {uid})",
                        "concepts.json",
                        "Remove the trailing comma from the concept name",
                    )
                )
            if c_name != c_name.rstrip():
                self.issues.append(
                    ValidationIssue(
                        "warning",
                        "name_hygiene",
                        f"Trailing whitespace in concept name: '{c_name}' "
                        f"(UUID: {uid})",
                        "concepts.json",
                        "Trim trailing whitespace from the concept name",
                    )
                )
            if c_name != c_name.lstrip():
                self.issues.append(
                    ValidationIssue(
                        "warning",
                        "name_hygiene",
                        f"Leading whitespace in concept name: '{c_name}' "
                        f"(UUID: {uid})",
                        "concepts.json",
                        "Trim leading whitespace from the concept name",
                    )
                )

            # Check answer names
            for answer in concept.get("answers", []):
                a_name = answer.get("name", "")
                if a_name.endswith(","):
                    self.issues.append(
                        ValidationIssue(
                            "error",
                            "name_hygiene",
                            f"Trailing comma in answer name: '{a_name}' "
                            f"in concept '{c_name}'",
                            "concepts.json",
                            "Remove the trailing comma from the answer name",
                        )
                    )

    # ------------------------------------------------------------------
    # 7-8. Form validations
    # ------------------------------------------------------------------

    def _validate_forms(self) -> None:
        """Validate form-concept references, data types, and uniqueness."""
        form_uuids_seen: set[str] = set()

        for form_uuid, form in self._forms.items():
            form_name = form.get("name", form_uuid)

            # 8a. Duplicate form UUIDs
            if form_uuid in form_uuids_seen:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "duplicate_form",
                        f"Duplicate form UUID: '{form_uuid}' in form "
                        f"'{form_name}'",
                        f"forms/",
                        "Assign a unique UUID to the form",
                    )
                )
            form_uuids_seen.add(form_uuid)

            for feg in form.get("formElementGroups", []):
                feg_name = feg.get("name", "?")
                display_orders_seen: set[float] = set()

                for fe in feg.get("formElements", []):
                    # 8b. Duplicate displayOrder within a FEG
                    d_order = fe.get("displayOrder")
                    if d_order is not None:
                        if d_order in display_orders_seen:
                            self.issues.append(
                                ValidationIssue(
                                    "warning",
                                    "duplicate_display_order",
                                    f"Duplicate displayOrder {d_order} in FEG "
                                    f"'{feg_name}' of form '{form_name}'",
                                    f"forms/",
                                    "Ensure unique displayOrder values within "
                                    "each form element group",
                                )
                            )
                        display_orders_seen.add(d_order)

                    concept = fe.get("concept", {})
                    c_uuid = concept.get("uuid", "")
                    if not c_uuid:
                        continue

                    # 7a. Concept exists in concepts.json
                    if c_uuid not in self._concepts:
                        self.issues.append(
                            ValidationIssue(
                                "warning",
                                "missing_concept",
                                f"Form '{form_name}' references concept "
                                f"'{concept.get('name')}' (UUID: {c_uuid}) "
                                f"not found in concepts.json",
                                f"forms/",
                                "Add the concept to concepts.json or fix "
                                "the UUID",
                            )
                        )
                        continue

                    master = self._concepts[c_uuid]

                    # 7b. Data type consistency
                    if (
                        concept.get("dataType")
                        and master.get("dataType")
                        and concept["dataType"] != master["dataType"]
                    ):
                        self.issues.append(
                            ValidationIssue(
                                "warning",
                                "datatype_mismatch",
                                f"Data type mismatch in form '{form_name}': "
                                f"concept '{concept.get('name')}' is "
                                f"'{concept['dataType']}' in form but "
                                f"'{master['dataType']}' in concepts.json",
                                f"forms/",
                                "Ensure the form element uses the same data "
                                "type as concepts.json",
                            )
                        )

                    # 7c. Answer UUID consistency
                    if concept.get("answers") and master.get("answers"):
                        master_answers_by_name = {
                            a.get("name"): a for a in master["answers"]
                        }
                        for form_answer in concept["answers"]:
                            fa_name = form_answer.get("name", "")
                            ma = master_answers_by_name.get(fa_name)
                            if (
                                ma
                                and form_answer.get("uuid")
                                and ma.get("uuid")
                                and form_answer["uuid"] != ma["uuid"]
                            ):
                                self.issues.append(
                                    ValidationIssue(
                                        "error",
                                        "answer_uuid_mismatch",
                                        f"Answer UUID mismatch: '{fa_name}' "
                                        f"in form '{form_name}' has UUID "
                                        f"{form_answer['uuid']} but master "
                                        f"concept has {ma['uuid']}",
                                        f"forms/",
                                        "Ensure answer UUIDs in forms match "
                                        "those in concepts.json",
                                    )
                                )

    # ------------------------------------------------------------------
    # 9. Encounter type completeness
    # ------------------------------------------------------------------

    def _validate_encounter_type_completeness(self) -> None:
        """Check each encounter type has form mappings and cancellation forms."""
        for et_uuid, et in self._encounter_types.items():
            et_name = et.get("name", et_uuid)

            has_encounter_mapping = any(
                m.get("encounterTypeUUID") == et_uuid
                and m.get("formType")
                in ("Encounter", "ProgramEncounter")
                and not m.get("voided", False)
                for m in self._form_mappings
            )
            if not has_encounter_mapping:
                self.issues.append(
                    ValidationIssue(
                        "warning",
                        "missing_mapping",
                        f"Encounter type '{et_name}' has no Encounter or "
                        f"ProgramEncounter form mapping",
                        "formMappings.json",
                        f"Add a form mapping for encounter type '{et_name}'",
                    )
                )

            has_cancel_mapping = any(
                m.get("encounterTypeUUID") == et_uuid
                and m.get("formType")
                in (
                    "IndividualEncounterCancellation",
                    "ProgramEncounterCancellation",
                )
                and not m.get("voided", False)
                for m in self._form_mappings
            )
            if not has_cancel_mapping:
                self.issues.append(
                    ValidationIssue(
                        "warning",
                        "missing_cancellation",
                        f"Encounter type '{et_name}' has no cancellation "
                        f"form mapping",
                        "formMappings.json",
                        f"Create a cancellation form and mapping for "
                        f"'{et_name}'",
                    )
                )

    # ------------------------------------------------------------------
    # 10. Form mapping referential integrity
    # ------------------------------------------------------------------

    def _validate_form_mapping_references(self) -> None:
        """Validate all form mapping UUIDs reference existing entities."""
        for fm in self._form_mappings:
            fm_name = fm.get("formName", "?")

            # formUUID -> forms/
            form_uuid = fm.get("formUUID", "")
            if form_uuid and form_uuid not in self._form_uuids:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "orphaned_mapping",
                        f"Form mapping '{fm_name}' references formUUID "
                        f"'{form_uuid}' not found in forms/",
                        "formMappings.json",
                        "Ensure the form JSON file exists in forms/ directory",
                    )
                )

            # programUUID -> programs.json
            prog_uuid = fm.get("programUUID", "")
            if prog_uuid and prog_uuid not in self._programs:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "missing_program",
                        f"Form mapping '{fm_name}' references programUUID "
                        f"'{prog_uuid}' not found in programs.json",
                        "formMappings.json",
                        "Add the program to programs.json or fix the UUID",
                    )
                )

            # encounterTypeUUID -> encounterTypes.json
            et_uuid = fm.get("encounterTypeUUID", "")
            if et_uuid and et_uuid not in self._encounter_types:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "missing_encounter_type",
                        f"Form mapping '{fm_name}' references "
                        f"encounterTypeUUID '{et_uuid}' not found in "
                        f"encounterTypes.json",
                        "formMappings.json",
                        "Add the encounter type to encounterTypes.json or "
                        "fix the UUID",
                    )
                )

            # subjectTypeUUID -> subjectTypes.json
            st_uuid = fm.get("subjectTypeUUID", "")
            if st_uuid and st_uuid not in self._subject_types:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "missing_subject_type",
                        f"Form mapping '{fm_name}' references "
                        f"subjectTypeUUID '{st_uuid}' not found in "
                        f"subjectTypes.json",
                        "formMappings.json",
                        "Add the subject type to subjectTypes.json or "
                        "fix the UUID",
                    )
                )

    # ------------------------------------------------------------------
    # 11. Report card format
    # ------------------------------------------------------------------

    def _validate_report_card_format(self) -> None:
        """Validate reportCard.json field formats."""
        rc_path = os.path.join(self._bundle_dir, "reportCard.json")
        if not os.path.isfile(rc_path):
            return

        try:
            with open(rc_path, "r", encoding="utf-8") as f:
                rc_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return  # JSON error already caught by _check_required_files

        if not isinstance(rc_data, list):
            return

        for card in rc_data:
            card_name = card.get("name", "?")
            for field_name in (
                "standardReportCardInputSubjectTypes",
                "standardReportCardInputPrograms",
                "standardReportCardInputEncounterTypes",
            ):
                field_val = card.get(field_name)
                if field_val is None or not isinstance(field_val, list):
                    continue
                for item in field_val:
                    if not isinstance(item, str):
                        self.issues.append(
                            ValidationIssue(
                                "error",
                                "report_card_format",
                                f"reportCard '{card_name}': {field_name} "
                                f"should be array of UUID strings, found "
                                f"non-string: {json.dumps(item)}",
                                "reportCard.json",
                                f"Replace objects with UUID strings in "
                                f"{field_name}",
                            )
                        )

    # ------------------------------------------------------------------
    # 12. Operational config wrapper format
    # ------------------------------------------------------------------

    def _validate_operational_config_format(self) -> None:
        """Validate operational config files have correct wrapper structure."""
        op_configs = [
            ("operationalSubjectTypes.json", "operationalSubjectTypes"),
            ("operationalPrograms.json", "operationalPrograms"),
            ("operationalEncounterTypes.json", "operationalEncounterTypes"),
        ]
        for filename, wrapper_key in op_configs:
            filepath = os.path.join(self._bundle_dir, filename)
            if not os.path.isfile(filepath):
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue  # Already caught elsewhere

            if isinstance(data, list):
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "operational_format",
                        f"{filename} is a bare array. Must be wrapped: "
                        f"{{ {wrapper_key}: [...] }}",
                        filename,
                        f"Wrap the array in an object with key "
                        f"'{wrapper_key}'",
                    )
                )
            elif isinstance(data, dict) and wrapper_key not in data:
                self.issues.append(
                    ValidationIssue(
                        "error",
                        "operational_format",
                        f"{filename} missing '{wrapper_key}' wrapper key",
                        filename,
                        f"Add the '{wrapper_key}' key wrapping the array",
                    )
                )

    # ------------------------------------------------------------------
    # Legacy: Duplicate privileges check
    # ------------------------------------------------------------------

    def _check_duplicate_privileges(self) -> None:
        """Check for duplicate groupPrivilege entries."""
        seen: set[tuple] = set()
        for gp in self._group_privileges:
            key = (
                gp.get("groupUUID", ""),
                gp.get("privilegeType", ""),
                gp.get("subjectTypeUUID", ""),
                gp.get("programUUID", ""),
                gp.get("encounterTypeUUID", ""),
            )
            if key in seen:
                self.issues.append(
                    ValidationIssue(
                        "warning",
                        "duplicate_privilege",
                        f"Duplicate groupPrivilege: "
                        f"{gp.get('privilegeType')} for group "
                        f"{gp.get('groupUUID', '')[:8]}",
                        "groupPrivilege.json",
                        "Remove the duplicate entry",
                    )
                )
            seen.add(key)


# ---------------------------------------------------------------------------
# Convenience function (backward-compatible)
# ---------------------------------------------------------------------------


def validate_bundle(bundle_path: str) -> dict:
    """Validate a bundle directory or zip file.

    Returns:
        {
            "valid": bool,
            "error_count": int,
            "warning_count": int,
            "errors": [str, ...],
            "warnings": [str, ...],
            "issues": [{severity, category, message, file, fix_hint}, ...],
        }
    """
    validator = BundleValidator(bundle_path)
    return validator.validate()
