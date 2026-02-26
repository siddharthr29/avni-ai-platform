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
)

logger = logging.getLogger(__name__)

# Keys whose numeric values should always have .0 suffix (float format in Avni)
FLOAT_KEYS = {"level", "displayOrder", "order", "lowAbsolute", "highAbsolute"}

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

    def stable_uuid(self, key: str) -> str:
        if key not in self._cache:
            # Check if this is a concept key that matches a known answer
            if key.startswith("concept:"):
                concept_name = key[len("concept:"):]
                standard = self._standard_uuids.get(concept_name)
                if standard:
                    self._cache[key] = standard
                    return self._cache[key]
            self._cache[key] = _new_uuid()
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
    ) -> dict[str, Any]:
        key = f"concept:{name}"
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
        if data_type == "Coded":
            concept["answers"] = []
        self._concepts[key] = concept
        return concept

    def get_or_create_answer(self, name: str) -> dict[str, Any]:
        key = f"concept:{name}"
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
    ) -> dict[str, Any]:
        concept = self.get_or_create(
            concept_name, "Coded", unit=unit,
            low_absolute=low_absolute, high_absolute=high_absolute,
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
        result = []
        for c in self._concepts.values():
            concept: dict[str, Any] = {
                "name": c["name"],
                "uuid": c["uuid"],
                "dataType": c["dataType"],
                "active": c["active"],
            }
            if c.get("unit"):
                concept["unit"] = c["unit"]
            if c.get("lowAbsolute") is not None:
                concept["lowAbsolute"] = c["lowAbsolute"]
            if c.get("highAbsolute") is not None:
                concept["highAbsolute"] = c["highAbsolute"]
            if c["dataType"] == "Coded" and c.get("answers"):
                concept["answers"] = [
                    {"name": a["name"], "uuid": a["uuid"], "order": a["order"]}
                    for a in c["answers"]
                ]
            result.append(concept)
        return result


def _build_form_element(
    field: SRSFormField,
    display_order: int,
    concepts: ConceptManager,
    registry: UUIDRegistry,
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

    # Build form element concept representation
    form_concept: dict[str, Any] = {
        "name": concept["name"],
        "uuid": concept["uuid"],
        "dataType": concept["dataType"],
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
                "answers": [],
                "order": a["order"],
                "active": True,
                "media": [],
            }
            for a in concept["answers"]
        ]

    element_type = field.type or "SingleSelect"
    if field.dataType == "Coded" and field.type is None:
        element_type = "SingleSelect"

    element: dict[str, Any] = {
        "name": field.name,
        "uuid": registry.new_uuid(),
        "keyValues": field.keyValues or [],
        "concept": form_concept,
        "displayOrder": float(display_order),
        "type": element_type,
        "mandatory": field.mandatory,
    }

    return element


def _build_form(
    form_def: SRSFormDefinition,
    form_uuid: str,
    concepts: ConceptManager,
    registry: UUIDRegistry,
) -> dict[str, Any]:
    """Build a complete form JSON from a form definition."""
    form_element_groups = []
    for gi, group in enumerate(form_def.groups):
        elements = []
        for fi, field in enumerate(group.fields):
            elements.append(
                _build_form_element(field, fi + 1, concepts, registry)
            )
        form_element_groups.append({
            "uuid": registry.new_uuid(),
            "name": group.name,
            "displayOrder": float(gi + 1),
            "formElements": elements,
        })

    return {
        "name": form_def.name,
        "uuid": form_uuid,
        "formType": form_def.formType,
        "formElementGroups": form_element_groups,
    }


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
        {"uuid": state_uuid, "name": "State", "level": 3.0},
        {
            "uuid": district_uuid,
            "name": "District",
            "level": 2.0,
            "parent": {"uuid": state_uuid},
        },
        {
            "uuid": block_uuid,
            "name": "Block",
            "level": 1.0,
            "parent": {"uuid": district_uuid},
        },
    ]


def generate_subject_types(
    srs: SRSData, registry: UUIDRegistry,
) -> list[dict[str, Any]]:
    """Generate subjectTypes.json content."""
    result = []
    for st in srs.subjectTypes:
        name = st.get("name", "Individual")
        result.append({
            "name": name,
            "uuid": registry.stable_uuid(f"subjectType:{name}"),
            "active": True,
            "type": st.get("type", "Person"),
            "subjectSummaryRule": "",
            "programEligibilityCheckRule": "",
            "allowEmptyLocation": False,
            "allowMiddleName": True,
            "lastNameOptional": False,
            "allowProfilePicture": False,
            "uniqueName": False,
            "shouldSyncByLocation": True,
            "settings": {
                "displayRegistrationDetails": True,
                "displayPlannedEncounters": True,
            },
            "household": st.get("type") == "Household",
            "group": st.get("type") == "Group",
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
                "uuid": registry.new_uuid(),
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
                "uuid": registry.new_uuid(),
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
    """Generate encounterTypes.json content."""
    return [
        {
            "name": name,
            "uuid": registry.stable_uuid(f"encounterType:{name}"),
            "active": True,
            "immutable": False,
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
                "uuid": registry.new_uuid(),
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
) -> list[dict[str, Any]]:
    """Generate formMappings.json content."""
    mappings = []
    for fm in form_meta:
        mapping: dict[str, Any] = {
            "uuid": _new_uuid(),
            "formUUID": fm["formUUID"],
            "subjectTypeUUID": fm.get("subjectTypeUUID", primary_subject_type_uuid),
            "formType": fm["formType"],
            "formName": fm["formName"],
            "enableApproval": False,
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
        group: dict[str, Any] = {
            "uuid": registry.stable_uuid(f"group:{name}"),
            "name": name,
        }
        if name == "Everyone":
            group["notEveryoneGroup"] = False
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
                    "subjectTypeUUID": subject_type_uuid,
                    "allow": True,
                    "privilegeType": priv["name"],
                    "notEveryoneGroup": is_not_everyone,
                    "voided": False,
                })

            elif priv["level"] == "program":
                for prog in programs:
                    privileges.append({
                        "uuid": _new_uuid(),
                        "groupUUID": group_uuid,
                        "privilegeUUID": priv_uuid,
                        "subjectTypeUUID": subject_type_uuid,
                        "programUUID": prog["uuid"],
                        "allow": True,
                        "privilegeType": priv["name"],
                        "notEveryoneGroup": is_not_everyone,
                        "voided": False,
                    })

            elif priv["level"] == "encounterType":
                # Program encounter types
                for mapping in pe_mappings:
                    prog_name = mapping.get("program", "")
                    for et_name in mapping.get("encounterTypes", []):
                        privileges.append({
                            "uuid": _new_uuid(),
                            "groupUUID": group_uuid,
                            "privilegeUUID": priv_uuid,
                            "subjectTypeUUID": subject_type_uuid,
                            "programUUID": registry.stable_uuid(
                                f"program:{prog_name}"
                            ),
                            "encounterTypeUUID": registry.stable_uuid(
                                f"encounterType:{et_name}"
                            ),
                            "allow": True,
                            "privilegeType": priv["name"],
                            "notEveryoneGroup": is_not_everyone,
                            "voided": False,
                        })

                # General encounter types (no program)
                for et_name in ge_types:
                    privileges.append({
                        "uuid": _new_uuid(),
                        "groupUUID": group_uuid,
                        "privilegeUUID": priv_uuid,
                        "subjectTypeUUID": subject_type_uuid,
                        "encounterTypeUUID": registry.stable_uuid(
                            f"encounterType:{et_name}"
                        ),
                        "allow": True,
                        "privilegeType": priv["name"],
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


def create_bundle_zip(output_dir: str, bundle_id: str) -> str:
    """Create an ordered zip file from the generated bundle files.

    Returns the path to the zip file.
    """
    zip_path = os.path.join(output_dir, f"{bundle_id}.zip")

    # Files in exact dependency order (matching BundleService.createBundle() export order)
    ordered_files = [
        "addressLevelTypes.json",
        "subjectTypes.json",
        "operationalSubjectTypes.json",
        "encounterTypes.json",
        "operationalEncounterTypes.json",
        "programs.json",
        "operationalPrograms.json",
        "concepts.json",
    ]

    # Add form files
    forms_dir = os.path.join(output_dir, bundle_id, "forms")
    if os.path.isdir(forms_dir):
        form_files = sorted(
            f for f in os.listdir(forms_dir) if f.endswith(".json")
        )
        for f in form_files:
            ordered_files.append(os.path.join("forms", f))

    # Remaining files in dependency order
    ordered_files.extend([
        "formMappings.json",
        "groups.json",
        "groupPrivilege.json",
    ])

    bundle_dir = os.path.join(output_dir, bundle_id)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel_path in ordered_files:
            full_path = os.path.join(bundle_dir, rel_path)
            if os.path.isfile(full_path):
                zf.write(full_path, rel_path)
            else:
                logger.warning("Bundle file not found, skipping: %s", full_path)

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
        primary_st_uuid = subject_types[0]["uuid"]

        # 3. Operational subject types
        _update_status(bundle_id, 15, "Generating operational subject types...")
        op_subject_types = generate_operational_subject_types(subject_types, registry)
        _write("operationalSubjectTypes.json", op_subject_types)

        # 4. Encounter types
        _update_status(bundle_id, 20, "Generating encounter types...")
        encounter_types = generate_encounter_types(srs, registry)
        _write("encounterTypes.json", encounter_types)

        # 5. Operational encounter types
        _update_status(bundle_id, 25, "Generating operational encounter types...")
        op_encounter_types = generate_operational_encounter_types(
            encounter_types, registry
        )
        _write("operationalEncounterTypes.json", op_encounter_types)

        # 6. Programs
        _update_status(bundle_id, 30, "Generating programs...")
        programs = generate_programs(srs, registry)
        _write("programs.json", programs)

        # 7. Operational programs
        _update_status(bundle_id, 35, "Generating operational programs...")
        op_programs = generate_operational_programs(programs, registry)
        _write("operationalPrograms.json", op_programs)

        # 8. Forms (and build concept registry along the way)
        _update_status(bundle_id, 40, "Generating forms...")
        form_meta: list[dict[str, Any]] = []
        total_forms = len(srs.forms)

        for i, form_def in enumerate(srs.forms):
            form_uuid = registry.stable_uuid(f"form:{form_def.name}")
            form_json = _build_form(form_def, form_uuid, concepts, registry)
            _write(f"forms/{form_def.name}.json", form_json)

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
            form_meta.append(meta)

            progress = 40 + int(30 * (i + 1) / max(total_forms, 1))
            _update_status(
                bundle_id, progress, f"Generated form {i + 1}/{total_forms}: {form_def.name}"
            )

        # 9. Concepts (collected from all forms)
        _update_status(bundle_id, 75, "Generating concepts...")
        concepts_list = concepts.all_concepts()
        _write("concepts.json", concepts_list)

        # 10. Form mappings
        _update_status(bundle_id, 80, "Generating form mappings...")
        form_mappings = generate_form_mappings(form_meta, primary_st_uuid)
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

        # 13. Create zip
        _update_status(bundle_id, 95, "Creating zip file...")
        zip_path = create_bundle_zip(settings.BUNDLE_OUTPUT_DIR, bundle_id)

        _bundle_store[bundle_id] = BundleStatus(
            id=bundle_id,
            status=BundleStatusType.COMPLETED,
            progress=100,
            message=f"Bundle generated: {len(concepts_list)} concepts, "
                    f"{total_forms} forms, {len(form_mappings)} mappings, "
                    f"{len(group_privileges)} privileges",
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
