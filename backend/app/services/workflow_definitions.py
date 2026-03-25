"""
Pre-built workflow definitions for common Avni AI flows.

Each function returns a Workflow with the appropriate steps and checkpoint
levels. The step executors reference the shared workflow context dict to
pass data between steps.
"""

import logging
import uuid
from typing import Any

from app.services.workflow_engine import (
    CheckpointLevel,
    Workflow,
    WorkflowStep,
    workflow_engine,
)

logger = logging.getLogger(__name__)


# ── Step Executors ────────────────────────────────────────────────────────────
# Each executor is an async function: (context: dict) -> Any
# They read from and write to the shared context dict.


async def parse_srs_step(context: dict) -> dict:
    """Parse SRS text or Excel data into structured SRSData."""
    from app.models.schemas import SRSData

    # If srs_data is already structured, pass through
    if "srs_data" in context and isinstance(context["srs_data"], dict):
        srs_dict = context["srs_data"]
        srs = SRSData(**srs_dict)
        context["parsed_srs"] = srs
        return {
            "org_name": srs.orgName,
            "forms_count": len(srs.forms),
            "programs": [
                p.get("name", p) if isinstance(p, dict) else p
                for p in srs.programs
            ],
            "encounter_types": srs.encounterTypes,
        }

    # Parse from text using LLM
    if "srs_text" in context:
        from app.routers.bundle import _parse_srs_text

        srs = await _parse_srs_text(context["srs_text"])
        context["parsed_srs"] = srs
        return {
            "org_name": srs.orgName,
            "forms_count": len(srs.forms),
            "programs": [
                p.get("name", p) if isinstance(p, dict) else p
                for p in srs.programs
            ],
            "encounter_types": srs.encounterTypes,
        }

    raise ValueError("No SRS data or text provided in workflow context")


async def detect_gaps_step(context: dict) -> dict:
    """Detect gaps and ambiguities in the parsed SRS data.

    Returns a dict with questions (if any). If questions exist, the BLOCK
    checkpoint will pause the workflow for human input.
    """
    from app.routers.bundle import _validate_srs_quality

    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    issues = _validate_srs_quality(srs)
    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]

    questions = []
    for issue in issues:
        if issue.get("suggestion") and issue["severity"] in ("error", "warning"):
            questions.append({
                "question": issue["suggestion"],
                "context": issue["message"],
                "field": issue.get("field"),
            })

    context["srs_issues"] = issues
    context["srs_questions"] = questions

    result = {
        "errors": len(errors),
        "warnings": len(warnings),
        "total_issues": len(issues),
        "questions": questions,
        "has_blocking_issues": len(errors) > 0 or len(questions) > 0,
    }

    # If no gaps found, this step can be auto-approved
    if not questions:
        result["auto_approved"] = True

    return result


async def generate_concepts_step(context: dict) -> dict:
    """Generate Avni concept definitions from the parsed SRS."""
    from app.services.bundle_generator import ConceptManager, UUIDRegistry

    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    registry = UUIDRegistry()
    concept_mgr = ConceptManager(registry)

    # Build concepts from all forms
    for form in srs.forms:
        for group in form.groups:
            for fld in group.fields:
                if fld.dataType == "Coded" and fld.options:
                    concept_mgr.ensure_coded_with_answers(
                        concept_name=fld.name,
                        answer_names=fld.options,
                        unit=fld.unit,
                        low_absolute=fld.lowAbsolute,
                        high_absolute=fld.highAbsolute,
                    )
                else:
                    concept_mgr.get_or_create(
                        name=fld.name,
                        data_type=fld.dataType or "Text",
                        unit=fld.unit,
                        low_absolute=fld.lowAbsolute,
                        high_absolute=fld.highAbsolute,
                    )

    concepts = concept_mgr.all_concepts()
    context["concepts"] = concepts
    context["uuid_registry"] = registry
    context["concept_manager"] = concept_mgr

    return {
        "total_concepts": len(concepts),
        "coded_concepts": sum(
            1 for c in concepts if c.get("dataType") == "Coded"
        ),
        "numeric_concepts": sum(
            1 for c in concepts if c.get("dataType") == "Numeric"
        ),
    }


async def validate_concepts(result: Any, context: dict) -> tuple[bool, list, list]:
    """Validate generated concepts for duplicates and issues."""
    concepts = context.get("concepts", [])
    errors = []
    warnings = []

    # Check for name collisions
    seen_names: dict[str, int] = {}
    for c in concepts:
        name = c.get("name", "")
        seen_names[name] = seen_names.get(name, 0) + 1

    for name, count in seen_names.items():
        if count > 1:
            errors.append(f"Duplicate concept name: '{name}' (appears {count} times)")

    # Check for empty names
    for c in concepts:
        if not c.get("name", "").strip():
            errors.append(f"Concept with empty name found (UUID: {c.get('uuid', 'unknown')})")

    # Warn about coded concepts without answers
    for c in concepts:
        if c.get("dataType") == "Coded" and not c.get("answers"):
            warnings.append(f"Coded concept '{c.get('name')}' has no answer options")

    return len(errors) == 0, errors, warnings


async def fix_concept_collisions(
    result: Any, errors: list, context: dict,
) -> dict:
    """Auto-fix concept name collisions by appending form context."""
    concepts = context.get("concepts", [])
    seen: dict[str, list[int]] = {}

    for i, c in enumerate(concepts):
        name = c.get("name", "")
        if name not in seen:
            seen[name] = []
        seen[name].append(i)

    fixed_count = 0
    for name, indices in seen.items():
        if len(indices) > 1:
            for idx in indices[1:]:
                old_name = concepts[idx]["name"]
                # Append a disambiguator
                concepts[idx]["name"] = f"{old_name} ({idx})"
                fixed_count += 1

    context["concepts"] = concepts
    logger.info("Fixed %d concept name collisions", fixed_count)
    return result


async def generate_forms_step(context: dict) -> dict:
    """Generate Avni form JSON definitions from the parsed SRS."""
    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    from app.services.bundle_generator import generate_from_srs, _bundle_store

    # We build form JSON structures here
    forms_generated = []
    for form_def in srs.forms:
        forms_generated.append({
            "name": form_def.name,
            "formType": form_def.formType,
            "programName": form_def.programName,
            "encounterTypeName": form_def.encounterTypeName,
            "groups_count": len(form_def.groups),
            "fields_count": sum(len(g.fields) for g in form_def.groups),
        })

    context["forms_summary"] = forms_generated
    return {
        "total_forms": len(forms_generated),
        "forms": forms_generated,
    }


async def validate_forms(result: Any, context: dict) -> tuple[bool, list, list]:
    """Validate generated forms for structural issues."""
    errors = []
    warnings = []
    srs = context.get("parsed_srs")

    if srs:
        for form in srs.forms:
            if not form.groups:
                warnings.append(f"Form '{form.name}' has no field groups")
            total_fields = sum(len(g.fields) for g in form.groups)
            if total_fields == 0:
                warnings.append(f"Form '{form.name}' has no fields")
            if form.formType in ("ProgramEnrolment", "ProgramExit", "ProgramEncounter") and not form.programName:
                errors.append(f"Form '{form.name}' (type {form.formType}) is missing programName")

    return len(errors) == 0, errors, warnings


async def generate_rules_step(context: dict) -> dict:
    """Generate skip logic and decision-support rules."""
    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    rules_count = 0
    rules_summary = []

    # Check for skip logic fields
    for form in srs.forms:
        for group in form.groups:
            for field in group.fields:
                if field.keyValues:
                    for kv in field.keyValues:
                        if kv.get("key") in ("showWhen", "hideWhen"):
                            rules_count += 1
                            rules_summary.append({
                                "form": form.name,
                                "field": field.name,
                                "type": kv["key"],
                            })

    context["rules_summary"] = rules_summary
    return {
        "total_rules": rules_count,
        "rules": rules_summary,
    }


async def validate_rules(result: Any, context: dict) -> tuple[bool, list, list]:
    """Validate generated rules for syntax and reference issues."""
    errors = []
    warnings = []
    rules = context.get("rules_summary", [])

    for rule in rules:
        if not rule.get("field"):
            errors.append(f"Rule in form '{rule.get('form')}' has no target field")

    if not rules:
        warnings.append("No skip logic rules detected. This may be intentional.")

    return len(errors) == 0, errors, warnings


async def preflight_validate_step(context: dict) -> dict:
    """Run final pre-flight validation before packaging."""
    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    checks = {
        "has_forms": len(srs.forms) > 0,
        "has_subject_types": len(srs.subjectTypes) > 0,
        "all_forms_have_fields": all(
            sum(len(g.fields) for g in f.groups) > 0
            for f in srs.forms
        ),
        "concepts_generated": "concepts" in context,
    }

    all_passed = all(checks.values())
    context["preflight_passed"] = all_passed

    return {
        "passed": all_passed,
        "checks": checks,
    }


async def package_bundle_step(context: dict) -> dict:
    """Package all generated artifacts into a bundle zip."""
    import os

    from app.config import settings
    from app.models.schemas import BundleStatusType
    from app.services.bundle_generator import generate_from_srs, get_bundle_status

    srs = context.get("parsed_srs")
    if srs is None:
        raise ValueError("No parsed SRS data available")

    bundle_id = context.get("bundle_id", str(uuid.uuid4()))
    context["bundle_id"] = bundle_id

    # Run the actual bundle generator
    await generate_from_srs(srs, bundle_id)

    # Check the result
    status = get_bundle_status(bundle_id)
    if status and status.status == BundleStatusType.FAILED:
        raise RuntimeError(f"Bundle generation failed: {status.message}")

    bundle_dir = os.path.join(settings.BUNDLE_OUTPUT_DIR, bundle_id)
    context["bundle_dir"] = bundle_dir
    context["bundle_status"] = status

    return {
        "bundle_id": bundle_id,
        "status": status.status.value if status else "unknown",
        "message": status.message if status else "",
    }


async def present_bundle_summary_step(context: dict) -> dict:
    """Present a summary of the generated bundle for human review."""
    import os

    bundle_dir = context.get("bundle_dir", "")
    bundle_id = context.get("bundle_id", "unknown")
    srs = context.get("parsed_srs")

    # Count files in the bundle
    file_count = 0
    file_types: dict[str, int] = {}
    if os.path.isdir(bundle_dir):
        for root, _dirs, files in os.walk(bundle_dir):
            for f in files:
                file_count += 1
                ext = os.path.splitext(f)[1]
                file_types[ext] = file_types.get(ext, 0) + 1

    summary = {
        "bundle_id": bundle_id,
        "total_files": file_count,
        "file_types": file_types,
    }

    if srs:
        summary.update({
            "org_name": srs.orgName,
            "forms_count": len(srs.forms),
            "programs": [
                p.get("name", p) if isinstance(p, dict) else p
                for p in srs.programs
            ],
            "encounter_types": srs.encounterTypes,
            "subject_types": [
                st.get("name", "") for st in srs.subjectTypes
            ],
        })

    context["bundle_summary"] = summary
    return summary


async def upload_to_avni_step(context: dict) -> dict:
    """Upload the bundle to Avni server.

    Requires org_context with avni_auth_token in the workflow context.
    """
    bundle_id = context.get("bundle_id")
    if not bundle_id:
        raise ValueError("No bundle_id in context")

    org_context = context.get("org_context", {})
    auth_token = org_context.get("avni_auth_token")
    if not auth_token:
        raise ValueError(
            "No Avni auth token provided. Set avni_auth_token in org_context "
            "to upload bundles."
        )

    from app.services.avni_org_service import upload_bundle_to_avni

    result = await upload_bundle_to_avni(bundle_id, auth_token)
    context["upload_result"] = result
    return result


# ── Workflow Builders ─────────────────────────────────────────────────────────


def create_bundle_generation_workflow(
    srs_data: dict | None = None,
    srs_text: str | None = None,
    org_context: dict | None = None,
) -> Workflow:
    """SRS -> Bundle -> Validate -> Review -> Upload workflow.

    Args:
        srs_data: Structured SRS data dict (if available).
        srs_text: Raw SRS text to be parsed by LLM (alternative to srs_data).
        org_context: Organisation context including auth tokens for upload.

    Returns:
        A Workflow registered with the workflow engine, ready to run.
    """
    context: dict[str, Any] = {}
    if srs_data:
        context["srs_data"] = srs_data
    if srs_text:
        context["srs_text"] = srs_text
    if org_context:
        context["org_context"] = org_context

    steps = [
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Parse SRS",
            description="Parse the SRS document into structured data",
            checkpoint=CheckpointLevel.AUTO,
            executor=parse_srs_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Detect Gaps & Ask Clarifications",
            description="Analyze SRS for missing data, ambiguities, and inconsistencies",
            checkpoint=CheckpointLevel.BLOCK,
            executor=detect_gaps_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Generate Concepts",
            description="Create Avni concept definitions from the SRS fields",
            checkpoint=CheckpointLevel.REVIEW,
            executor=generate_concepts_step,
            validator=validate_concepts,
            auto_fix=fix_concept_collisions,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Generate Forms",
            description="Build Avni form JSON structures from the SRS",
            checkpoint=CheckpointLevel.REVIEW,
            executor=generate_forms_step,
            validator=validate_forms,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Generate Rules",
            description="Generate skip logic and decision-support rules",
            checkpoint=CheckpointLevel.REVIEW,
            executor=generate_rules_step,
            validator=validate_rules,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Pre-flight Validation",
            description="Run final checks before packaging the bundle",
            checkpoint=CheckpointLevel.AUTO,
            executor=preflight_validate_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Package Bundle",
            description="Package all artifacts into a downloadable bundle zip",
            checkpoint=CheckpointLevel.AUTO,
            executor=package_bundle_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Review Bundle",
            description="Review the complete bundle before upload",
            checkpoint=CheckpointLevel.REVIEW,
            executor=present_bundle_summary_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Upload to Avni",
            description="Upload the validated bundle to the Avni server",
            checkpoint=CheckpointLevel.APPROVE,
            executor=upload_to_avni_step,
        ),
    ]

    return workflow_engine.create_workflow(
        name="Bundle Generation",
        steps=steps,
        context=context,
    )


def create_validation_only_workflow(
    srs_data: dict | None = None,
    srs_text: str | None = None,
) -> Workflow:
    """SRS -> Parse -> Validate workflow (no generation or upload).

    Useful for checking SRS quality before committing to full generation.
    """
    context: dict[str, Any] = {}
    if srs_data:
        context["srs_data"] = srs_data
    if srs_text:
        context["srs_text"] = srs_text

    steps = [
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Parse SRS",
            description="Parse the SRS document into structured data",
            checkpoint=CheckpointLevel.AUTO,
            executor=parse_srs_step,
        ),
        WorkflowStep(
            id=str(uuid.uuid4()),
            name="Detect Gaps & Ask Clarifications",
            description="Analyze SRS for missing data, ambiguities, and inconsistencies",
            checkpoint=CheckpointLevel.AUTO,
            executor=detect_gaps_step,
        ),
    ]

    return workflow_engine.create_workflow(
        name="SRS Validation",
        steps=steps,
        context=context,
    )
