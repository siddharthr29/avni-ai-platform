"""Bundle Review Wizard — interactive review step BEFORE bundle download.

Lets users verify and fix issues like wrong subject type mappings, missing
coded answer options, wrong form types, and missing programs.
"""

import json
import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import BundleStatus, BundleStatusType, SRSData
from app.services.bundle_generator import (
    generate_from_srs,
    get_bundle_status,
    _bundle_store,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers — read bundle JSON files from disk
# ---------------------------------------------------------------------------

def _read_bundle_json(bundle_dir: str, filename: str) -> Any:
    """Read and parse a JSON file from the bundle directory."""
    filepath = os.path.join(bundle_dir, filename)
    if not os.path.isfile(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_bundle_json(bundle_dir: str, filename: str, data: Any) -> None:
    """Write JSON data to a bundle file."""
    filepath = os.path.join(bundle_dir, filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _list_form_files(bundle_dir: str) -> list[str]:
    """List all form JSON files in the bundle's forms/ directory."""
    forms_dir = os.path.join(bundle_dir, "forms")
    if not os.path.isdir(forms_dir):
        return []
    return [f for f in os.listdir(forms_dir) if f.endswith(".json")]


def _verify_bundle_exists(bundle_id: str) -> str:
    """Verify bundle directory exists, return its path or raise 404."""
    bundle_dir = os.path.join(settings.BUNDLE_OUTPUT_DIR, bundle_id)
    if not os.path.isdir(bundle_dir):
        # Also check if the bundle is known but directory is gone
        status = get_bundle_status(bundle_id)
        if status is None:
            raise HTTPException(status_code=404, detail="Bundle not found")
        if status.status != BundleStatusType.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail=f"Bundle is not ready. Current status: {status.status.value}",
            )
        raise HTTPException(status_code=404, detail="Bundle directory not found on disk")
    return bundle_dir


# ---------------------------------------------------------------------------
# Build review summary from bundle files on disk
# ---------------------------------------------------------------------------

def _build_review_summary(bundle_id: str, bundle_dir: str) -> dict[str, Any]:
    """Analyze bundle files and produce a structured review summary."""
    subject_types_data = _read_bundle_json(bundle_dir, "subjectTypes.json") or []
    programs_data = _read_bundle_json(bundle_dir, "programs.json") or []
    encounter_types_data = _read_bundle_json(bundle_dir, "encounterTypes.json") or []
    form_mappings_data = _read_bundle_json(bundle_dir, "formMappings.json") or []
    concepts_data = _read_bundle_json(bundle_dir, "concepts.json") or []

    # Read all form files
    form_files = _list_form_files(bundle_dir)
    forms: list[dict[str, Any]] = []
    for fname in sorted(form_files):
        form_json = _read_bundle_json(bundle_dir, f"forms/{fname}")
        if form_json:
            forms.append(form_json)

    # Build UUID -> name lookups
    st_uuid_map = {st["uuid"]: st for st in subject_types_data}
    prog_uuid_map = {p["uuid"]: p for p in programs_data}
    et_uuid_map = {et["uuid"]: et for et in encounter_types_data}
    concept_name_map = {c["name"]: c for c in concepts_data}

    # Subject types summary
    subject_types_summary = []
    for st in subject_types_data:
        # Count how many form mappings reference this subject type
        st_forms = [
            fm for fm in form_mappings_data
            if fm.get("subjectTypeUUID") == st["uuid"]
        ]
        subject_types_summary.append({
            "name": st.get("name", "Unknown"),
            "type": st.get("type", "Person"),
            "uuid": st["uuid"],
            "forms_count": len(st_forms),
        })

    # Programs summary
    programs_summary = []
    for prog in programs_data:
        # Find encounter types linked to this program through form mappings
        prog_ets = set()
        for fm in form_mappings_data:
            if fm.get("programUUID") == prog["uuid"] and fm.get("encounterTypeUUID"):
                et = et_uuid_map.get(fm["encounterTypeUUID"])
                if et:
                    prog_ets.add(et.get("name", "Unknown"))
        programs_summary.append({
            "name": prog.get("name", "Unknown"),
            "uuid": prog["uuid"],
            "encounter_types": sorted(prog_ets),
        })

    # Form mappings summary with issue detection
    form_mappings_summary = []
    warnings: list[str] = []
    errors: list[str] = []
    coded_fields_needing_options: list[dict[str, Any]] = []

    for fm in form_mappings_data:
        form_uuid = fm.get("formUUID", "")
        form_type = fm.get("formType", "Unknown")
        form_name = fm.get("formName", "Unknown")

        # Resolve subject type
        st_uuid = fm.get("subjectTypeUUID")
        st_name = st_uuid_map.get(st_uuid, {}).get("name", "Unknown") if st_uuid else None

        # Resolve program
        prog_uuid = fm.get("programUUID")
        prog_name = prog_uuid_map.get(prog_uuid, {}).get("name") if prog_uuid else None

        # Resolve encounter type
        et_uuid = fm.get("encounterTypeUUID")
        et_name = et_uuid_map.get(et_uuid, {}).get("name") if et_uuid else None

        # Count fields in the form and find coded fields missing options
        field_count = 0
        coded_missing = []
        matching_form = None
        for form in forms:
            if form.get("uuid") == form_uuid or form.get("name") == form_name:
                matching_form = form
                break

        if matching_form:
            for fg in matching_form.get("formElementGroups", []):
                for fe in fg.get("formElements", []):
                    field_count += 1
                    concept = fe.get("concept", {})
                    c_name = concept.get("name", "")
                    c_dtype = concept.get("dataType", "")
                    if c_dtype == "Coded":
                        answers = concept.get("answers", [])
                        if not answers:
                            coded_missing.append(c_name)
                            coded_fields_needing_options.append({
                                "concept_name": c_name,
                                "form_name": form_name,
                                "current_options": [],
                            })

        form_mappings_summary.append({
            "form_name": form_name,
            "form_type": form_type,
            "subject_type": st_name,
            "program": prog_name,
            "encounter_type": et_name,
            "field_count": field_count,
            "coded_fields_missing_options": coded_missing,
        })

    # Detect warnings and errors
    for fm_s in form_mappings_summary:
        if fm_s["coded_fields_missing_options"]:
            for cf in fm_s["coded_fields_missing_options"]:
                warnings.append(
                    f"Coded field '{cf}' in form '{fm_s['form_name']}' has no answer options"
                )

        # Check for form type mismatches
        ft = fm_s["form_type"]
        if ft in ("ProgramEnrolment", "ProgramExit", "ProgramEncounter",
                   "ProgramEncounterCancellation") and not fm_s["program"]:
            errors.append(
                f"Form '{fm_s['form_name']}' has type '{ft}' but no program assigned"
            )

        if ft in ("ProgramEncounter", "ProgramEncounterCancellation",
                   "Encounter", "IndividualEncounterCancellation") and not fm_s["encounter_type"]:
            warnings.append(
                f"Form '{fm_s['form_name']}' has type '{ft}' but no encounter type"
            )

        if not fm_s["subject_type"]:
            warnings.append(
                f"Form '{fm_s['form_name']}' has no subject type assigned"
            )

    # Check for programs with no forms
    program_names_in_mappings = {fm_s["program"] for fm_s in form_mappings_summary if fm_s["program"]}
    for prog in programs_summary:
        if prog["name"] not in program_names_in_mappings:
            warnings.append(f"Program '{prog['name']}' has no forms linked to it")

    # Deduplicate coded_fields_needing_options by concept name
    seen_concepts: set[str] = set()
    unique_coded: list[dict[str, Any]] = []
    for cf in coded_fields_needing_options:
        if cf["concept_name"] not in seen_concepts:
            seen_concepts.add(cf["concept_name"])
            unique_coded.append(cf)

    return {
        "bundle_id": bundle_id,
        "subject_types": subject_types_summary,
        "programs": programs_summary,
        "form_mappings": form_mappings_summary,
        "warnings": warnings,
        "errors": errors,
        "coded_fields_needing_options": unique_coded,
    }


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class FixItem(BaseModel):
    type: str = Field(description="Fix type: set_subject_type, set_form_type, add_coded_options, add_program")
    form_name: str | None = Field(default=None, description="Target form name")
    subject_type: str | None = Field(default=None, description="New subject type name")
    new_form_type: str | None = Field(default=None, description="New form type")
    program: str | None = Field(default=None, description="Program name")
    encounter_type: str | None = Field(default=None, description="Encounter type name")
    concept_name: str | None = Field(default=None, description="Concept name for coded options fix")
    options: list[str] | None = Field(default=None, description="New coded answer options")
    name: str | None = Field(default=None, description="Entity name (for add_program)")


class FixRequest(BaseModel):
    fixes: list[FixItem] = Field(description="List of fixes to apply")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/bundle/review/{bundle_id}/summary")
async def review_summary(bundle_id: str) -> dict:
    """Return a structured review summary of a generated bundle.

    Analyzes the bundle files on disk and returns subject types, programs,
    form mappings, warnings, errors, and coded fields needing options.
    Caches the summary in Redis for subsequent review steps.
    """
    bundle_dir = _verify_bundle_exists(bundle_id)
    summary = _build_review_summary(bundle_id, bundle_dir)

    # Cache the review summary for fix/regenerate steps
    from app.services.cache import cache_bundle_review
    await cache_bundle_review(bundle_id, summary)

    return summary


@router.post("/bundle/review/{bundle_id}/fix")
async def apply_fixes(bundle_id: str, request: FixRequest) -> dict:
    """Apply user-specified fixes to a bundle and return the updated summary.

    Supported fix types:
    - set_subject_type: Change the subject type for a form mapping
    - set_form_type: Change the form type (and optionally program/encounter)
    - add_coded_options: Add answer options to a coded concept
    - add_program: Add a new program to the bundle
    """
    bundle_dir = _verify_bundle_exists(bundle_id)

    # Load current bundle data
    subject_types = _read_bundle_json(bundle_dir, "subjectTypes.json") or []
    programs = _read_bundle_json(bundle_dir, "programs.json") or []
    encounter_types = _read_bundle_json(bundle_dir, "encounterTypes.json") or []
    form_mappings = _read_bundle_json(bundle_dir, "formMappings.json") or []
    concepts = _read_bundle_json(bundle_dir, "concepts.json") or []
    op_programs = _read_bundle_json(bundle_dir, "operationalPrograms.json") or []

    # Build lookup maps
    st_name_map = {st["name"]: st for st in subject_types}
    prog_name_map = {p["name"]: p for p in programs}
    et_name_map = {et["name"]: et for et in encounter_types}
    concept_name_map = {c["name"]: c for c in concepts}

    changes_applied: list[str] = []

    for fix in request.fixes:
        if fix.type == "set_subject_type" and fix.form_name and fix.subject_type:
            # Find the form mapping and update its subject type UUID
            st = st_name_map.get(fix.subject_type)
            if not st:
                # Create a new subject type if it doesn't exist
                new_st_uuid = str(uuid.uuid5(
                    uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                    f"subjectType:{fix.subject_type}"
                ))
                new_st = {
                    "name": fix.subject_type,
                    "uuid": new_st_uuid,
                    "type": "Person",
                    "active": True,
                }
                subject_types.append(new_st)
                st_name_map[fix.subject_type] = new_st
                st = new_st

            for fm in form_mappings:
                if fm.get("formName") == fix.form_name:
                    fm["subjectTypeUUID"] = st["uuid"]
                    changes_applied.append(
                        f"Set subject type of '{fix.form_name}' to '{fix.subject_type}'"
                    )

        elif fix.type == "set_form_type" and fix.form_name and fix.new_form_type:
            for fm in form_mappings:
                if fm.get("formName") == fix.form_name:
                    fm["formType"] = fix.new_form_type
                    changes_applied.append(
                        f"Set form type of '{fix.form_name}' to '{fix.new_form_type}'"
                    )

                    # Update program reference if provided
                    if fix.program:
                        prog = prog_name_map.get(fix.program)
                        if prog:
                            fm["programUUID"] = prog["uuid"]
                            changes_applied.append(
                                f"Linked '{fix.form_name}' to program '{fix.program}'"
                            )

                    # Update encounter type reference if provided
                    if fix.encounter_type:
                        et = et_name_map.get(fix.encounter_type)
                        if et:
                            fm["encounterTypeUUID"] = et["uuid"]
                            changes_applied.append(
                                f"Linked '{fix.form_name}' to encounter type '{fix.encounter_type}'"
                            )

            # Also update the form JSON file itself
            for fname in _list_form_files(bundle_dir):
                form_json = _read_bundle_json(bundle_dir, f"forms/{fname}")
                if form_json and form_json.get("name") == fix.form_name:
                    form_json["formType"] = fix.new_form_type
                    _write_bundle_json(bundle_dir, f"forms/{fname}", form_json)

        elif fix.type == "add_coded_options" and fix.concept_name and fix.options:
            concept = concept_name_map.get(fix.concept_name)
            if concept:
                # Ensure concept is Coded type
                concept["dataType"] = "Coded"
                if "answers" not in concept:
                    concept["answers"] = []

                # Add new answer options
                existing_answer_names = {
                    a.get("answerConcept", {}).get("name", "")
                    for a in concept.get("answers", [])
                }
                for opt_name in fix.options:
                    if opt_name not in existing_answer_names:
                        # Create answer concept
                        answer_uuid = str(uuid.uuid5(
                            uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                            f"concept:{opt_name.lower()}"
                        ))
                        # Check if answer concept already exists in concepts list
                        answer_concept = concept_name_map.get(opt_name)
                        if not answer_concept:
                            answer_concept = {
                                "name": opt_name,
                                "uuid": answer_uuid,
                                "dataType": "NA",
                                "active": True,
                            }
                            concepts.append(answer_concept)
                            concept_name_map[opt_name] = answer_concept

                        concept["answers"].append({
                            "answerConcept": {
                                "name": opt_name,
                                "uuid": answer_concept["uuid"],
                            },
                            "unique": False,
                            "abnormal": False,
                            "order": len(concept["answers"]),
                        })

                changes_applied.append(
                    f"Added options {fix.options} to coded field '{fix.concept_name}'"
                )

                # Also update the concept in form files
                for fname in _list_form_files(bundle_dir):
                    form_json = _read_bundle_json(bundle_dir, f"forms/{fname}")
                    if not form_json:
                        continue
                    modified = False
                    for fg in form_json.get("formElementGroups", []):
                        for fe in fg.get("formElements", []):
                            if fe.get("concept", {}).get("name") == fix.concept_name:
                                fe["concept"]["dataType"] = "Coded"
                                fe["concept"]["answers"] = concept["answers"]
                                modified = True
                    if modified:
                        _write_bundle_json(bundle_dir, f"forms/{fname}", form_json)

        elif fix.type == "add_program" and fix.name:
            if fix.name not in prog_name_map:
                new_prog_uuid = str(uuid.uuid5(
                    uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890"),
                    f"program:{fix.name}"
                ))
                new_prog = {
                    "name": fix.name,
                    "uuid": new_prog_uuid,
                    "active": True,
                    "colour": "#E91E63",
                    "enrolmentSummaryRule": "",
                    "enrolmentEligibilityCheckRule": "",
                }
                programs.append(new_prog)
                prog_name_map[fix.name] = new_prog

                # Also add operational program
                op_prog = {
                    "name": fix.name,
                    "uuid": str(uuid.uuid4()),
                    "programUUID": new_prog_uuid,
                }
                op_programs.append(op_prog)

                changes_applied.append(f"Added program '{fix.name}'")

                # Link to subject type if specified
                if fix.subject_type:
                    st = st_name_map.get(fix.subject_type)
                    if st:
                        changes_applied.append(
                            f"Program '{fix.name}' associated with subject type '{fix.subject_type}'"
                        )

    # Write back all modified files
    _write_bundle_json(bundle_dir, "subjectTypes.json", subject_types)
    _write_bundle_json(bundle_dir, "programs.json", programs)
    _write_bundle_json(bundle_dir, "formMappings.json", form_mappings)
    _write_bundle_json(bundle_dir, "concepts.json", concepts)
    _write_bundle_json(bundle_dir, "operationalPrograms.json", op_programs)

    # Re-generate the summary after fixes
    updated_summary = _build_review_summary(bundle_id, bundle_dir)
    updated_summary["changes_applied"] = changes_applied
    return updated_summary


@router.post("/bundle/review/{bundle_id}/regenerate")
async def regenerate_bundle(
    bundle_id: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Regenerate the bundle with all applied fixes.

    Creates a new zip from the modified bundle files. Returns a new bundle_id
    that can be polled for status.
    """
    bundle_dir = _verify_bundle_exists(bundle_id)

    # Re-zip the bundle directory with all fixes applied
    import zipfile
    new_bundle_id = str(uuid.uuid4())
    zip_path = os.path.join(settings.BUNDLE_OUTPUT_DIR, f"{new_bundle_id}.zip")

    # Copy the fixed bundle to a new directory
    new_bundle_dir = os.path.join(settings.BUNDLE_OUTPUT_DIR, new_bundle_id)
    import shutil
    shutil.copytree(bundle_dir, new_bundle_dir)

    # Create the zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(new_bundle_dir):
            for f in files:
                file_path = os.path.join(root, f)
                arcname = os.path.relpath(file_path, settings.BUNDLE_OUTPUT_DIR)
                zf.write(file_path, arcname)

    # Register the new bundle in the in-memory store
    _bundle_store[new_bundle_id] = BundleStatus(
        id=new_bundle_id,
        status=BundleStatusType.COMPLETED,
        progress=100,
        message=f"Bundle regenerated from {bundle_id[:8]} with fixes applied",
        download_url=f"/api/bundle/{new_bundle_id}/download",
    )

    logger.info(
        "Regenerated bundle %s from %s with fixes", new_bundle_id, bundle_id
    )

    return {
        "original_bundle_id": bundle_id,
        "new_bundle_id": new_bundle_id,
        "status": "completed",
        "download_url": f"/api/bundle/{new_bundle_id}/download",
    }
