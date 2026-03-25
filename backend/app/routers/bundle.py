import asyncio
import json
import logging
import os
import tempfile
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response

from pydantic import BaseModel, Field

from app.config import settings
from app.db import (
    acquire_bundle_lock,
    get_bundle_lock,
    release_bundle_lock,
    cleanup_expired_locks,
)
from app.models.schemas import (
    BundleGenerateRequest,
    BundleStatus,
    BundleStatusType,
    SRSData,
)
from app.services.bundle_generator import (
    generate_from_srs,
    get_bundle_status,
    get_bundle_zip_path,
)
from app.services.claude_client import claude_client
from app.services.srs_parser import parse_srs_excel, parse_multiple_srs_excels

logger = logging.getLogger(__name__)

router = APIRouter()

SRS_PARSE_SYSTEM_PROMPT = """You are an expert at parsing Avni SRS (Scoping & Requirement Specification) documents into structured JSON.

## Avni Data Model
- Hierarchy: SubjectType → Program → EncounterType
- SubjectTypes: Person (Individual), Household, Group
- Each Program has: Enrolment form, Exit form, and one or more EncounterTypes
- Encounters under a program are "program encounters" (ProgramEncounter); standalone ones are "general encounters" (Encounter)

## SRS Document Structure
- **Modelling sheet**: defines SubjectTypes, Programs, and their EncounterTypes
- **Form sheets**: each form has fields with Page Name (group), Field Name, Data Type, Options, Mandatory, Skip Logic
- **Visit Scheduling sheet**: defines encounter frequencies (due days, overdue days)

## Form Types
| formType | Use |
|---|---|
| IndividualProfile | Subject registration |
| ProgramEnrolment | Enrolling in a program (needs programName) |
| ProgramExit | Exiting a program (needs programName) |
| ProgramEncounter | Visits within a program (needs programName + encounterTypeName) |
| ProgramEncounterCancellation | Cancelling a program visit (needs programName + encounterTypeName) |
| Encounter | General visits not under any program (needs encounterTypeName) |
| IndividualEncounterCancellation | Cancelling a general visit (needs encounterTypeName) |

## Data Type Mapping (SRS → Avni)
Map input data types to these Avni dataTypes:
- Pre-added Options / Single Select / Multi Select → **Coded** (set type: "SingleSelect" or "MultiSelect")
- Numeric / Number / Integer / Decimal / Auto-calculated → **Numeric**
- Text / Short text / Alpha Numeric → **Text**
- Long text / Notes → **Notes**
- Date / Calendar → **Date**
- DateTime → **DateTime**
- Image / Photo / Media → **Image**
- Phone / Mobile → **PhoneNumber**
- QuestionGroup → **QuestionGroup** (for repeatable sections, add keyValue: {"key": "repeatable", "value": true})

## JSON Output Schema
{
  "orgName": "Organisation Name",
  "subjectTypes": [{"name": "Individual", "type": "Person"}],
  "programs": [{"name": "Program Name", "colour": "#E91E63"}],
  "encounterTypes": ["Encounter Type 1"],
  "forms": [
    {
      "name": "Form Name",
      "formType": "IndividualProfile",
      "programName": "Program Name or null",
      "encounterTypeName": "Encounter Type Name or null",
      "groups": [
        {
          "name": "Group/Page Name",
          "fields": [
            {
              "name": "Field Name",
              "dataType": "Text|Numeric|Date|Coded|Notes|DateTime|Image|PhoneNumber|QuestionGroup",
              "mandatory": true,
              "options": ["Option1", "Option2"],
              "type": "SingleSelect|MultiSelect",
              "unit": "kg",
              "lowAbsolute": 0,
              "highAbsolute": 200,
              "keyValues": [{"key": "editable", "value": false}]
            }
          ]
        }
      ]
    }
  ],
  "groups": ["Everyone"],
  "addressLevelTypes": [
    {"name": "State", "level": 3},
    {"name": "District", "level": 2, "parent": "State"},
    {"name": "Block", "level": 1, "parent": "District"}
  ],
  "programEncounterMappings": [
    {"program": "Program Name", "encounterTypes": ["Encounter Type 1"]}
  ],
  "generalEncounterTypes": ["General Encounter"],
  "visitSchedules": [
    {"trigger": "ANC Visit", "schedule_encounter": "ANC Visit", "due_days": 30, "overdue_days": 45}
  ]
}

## Rules

### Forms & Structure
1. Include ALL forms: registration (IndividualProfile), program enrolment, exit, encounters, and cancellation forms.
2. For EVERY encounter type, generate BOTH the encounter form AND its cancellation form (ProgramEncounterCancellation or IndividualEncounterCancellation).
3. For EVERY program, generate BOTH the enrolment form AND the exit form.
4. Cancellation forms must have: "Cancellation Reason" (Coded, SingleSelect: Unavailable, Migrated, Refused, Other) and "Other Reason" (Text, mandatory=false, keyValues: [{"key": "showWhen", "value": "Cancellation Reason = Other"}]).
5. Group fields by Page Name / section from the SRS. Use descriptive group names.

### Mappings
6. programEncounterMappings: list every program with its encounter types. An encounter under a program must appear here.
7. generalEncounterTypes: list encounter types NOT under any program.
8. Always include an "Everyone" group in groups.

### Fields
9. Coded fields MUST include the options array. Set type to "SingleSelect" or "MultiSelect" based on context.
10. Numeric fields: include unit, lowAbsolute, highAbsolute when inferable. Use standard clinical ranges for health vitals (e.g., BP Systolic: 60-220 mmHg, Hemoglobin: 2-18 g/dL, Weight: 0-200 kg, Temperature: 35-42 °C, Birth Weight: 500-6000 grams).
11. Skip logic: encode as keyValues with {"key": "showWhen", "value": "ConceptName = Value"} or {"key": "hideWhen", "value": "..."}.
12. For repeatable/tabular sections, use dataType "QuestionGroup" with keyValues [{"key": "repeatable", "value": true}].

### Address Hierarchy
13. Higher level number = larger geography (State=3 > District=2 > Block=1). Include parent references.
14. Common patterns: Health NGO (State→District→Block→Village), ICDS (State→District→Project→Sector→AWC), Education (State→District→Block→Cluster→School).

### Visit Scheduling
15. Include visitSchedules when encounter frequency info is available. Format: {trigger, schedule_encounter, due_days, overdue_days}.
16. Common patterns: ANC 30/45 days, PNC 2-7/7-14 days, Growth Monitoring 30/45 days, Follow-up 14/21 days.

### Sector Patterns
When the domain is identifiable, apply these conventions:
- **MCH**: Programs like Maternal Health, Child Health. Encounters: ANC Visit, Delivery, PNC Visit, HBNC, Immunization.
- **Nutrition**: Growth Monitoring, SAM/MAM management, Supplementary Nutrition.
- **Livelihoods**: SHG/FPO management, Farm Visit, Training, Input Distribution.
- **Education**: Student tracking, Attendance, School inspections.

Respond with ONLY the JSON object, no other text."""


async def _parse_srs_text(srs_text: str) -> SRSData:
    """Use Claude to parse free-form SRS text into structured SRSData."""
    response_text = await claude_client.complete(
        messages=[{"role": "user", "content": srs_text}],
        system_prompt=SRS_PARSE_SYSTEM_PROMPT,
    )

    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

    data = json.loads(cleaned)
    return SRSData(**data)


async def _enrich_srs_fields(srs_data: SRSData) -> SRSData:
    """Run LLM Reasoner to enrich field properties (allowNegative, allowDecimal, etc.)."""
    try:
        from app.services.llm_reasoner import enrich_fields
        for form in srs_data.forms:
            for group in form.groups:
                group.fields = await enrich_fields(group.fields, use_llm=True)
        logger.info("LLM Reasoner enriched fields across %d forms", len(srs_data.forms))
    except Exception:
        logger.warning("LLM Reasoner failed, continuing with un-enriched fields", exc_info=True)
    return srs_data


async def _run_generation(srs_data: SRSData, bundle_id: str) -> None:
    """Background task to run bundle generation with LLM enrichment + skip logic."""
    try:
        # Phase 1: Enrich fields with inferred properties
        srs_data = await _enrich_srs_fields(srs_data)

        # Phase 2: Generate bundle
        await generate_from_srs(srs_data, bundle_id)

        # Phase 3: Generate skip logic rules from showWhen/hideWhen
        try:
            from app.services.skip_logic_generator import generate_skip_logic_for_bundle
            bundle_dir = os.path.join(settings.BUNDLE_OUTPUT_DIR, bundle_id)
            if os.path.isdir(bundle_dir):
                result = await generate_skip_logic_for_bundle(bundle_dir)
                logger.info(
                    "Skip logic: %d rules generated, %d failed",
                    result.get("rules_generated", 0),
                    result.get("rules_failed", 0),
                )
        except Exception:
            logger.warning("Skip logic generation failed, bundle still valid", exc_info=True)

    except Exception as e:
        logger.exception("Background bundle generation failed: %s", bundle_id)


@router.post("/bundle/generate", response_model=BundleStatus)
async def generate_bundle(
    request: BundleGenerateRequest,
    background_tasks: BackgroundTasks,
) -> BundleStatus:
    """Start bundle generation from SRS data or text.

    If srs_data is provided, it is used directly. If srs_text is provided,
    Claude parses it into structured SRS data first.

    Returns a BundleStatus with a bundle ID that can be polled for progress.
    """
    bundle_id = str(uuid.uuid4())

    if request.srs_data:
        srs_data = request.srs_data
    elif request.srs_text:
        try:
            srs_data = await _parse_srs_text(request.srs_text)
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Failed to parse SRS text into structured data: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Error processing SRS text: {str(e)}",
            )
    else:
        raise HTTPException(
            status_code=400,
            detail="Either srs_data or srs_text must be provided",
        )

    # Validate minimum viable SRS
    if not srs_data.forms:
        raise HTTPException(
            status_code=422,
            detail="SRS data must contain at least one form definition",
        )

    # Start generation in background
    status = BundleStatus(
        id=bundle_id,
        status=BundleStatusType.PENDING,
        progress=0,
        message="Bundle generation queued",
    )

    # Cache SRS for review wizard
    from app.services.cache import cache_parsed_srs
    await cache_parsed_srs(bundle_id, srs_data)

    background_tasks.add_task(_run_generation, srs_data, bundle_id)

    return status


@router.get("/bundle/{bundle_id}/status", response_model=BundleStatus)
async def bundle_status(bundle_id: str) -> BundleStatus:
    """Check the status and progress of a bundle generation job."""
    status = get_bundle_status(bundle_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return status


@router.get("/bundle/{bundle_id}/download")
async def download_bundle(bundle_id: str) -> FileResponse:
    """Download a completed bundle zip file."""
    status = get_bundle_status(bundle_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Bundle not found")

    if status.status != BundleStatusType.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Bundle is not ready yet. Current status: {status.status.value}",
        )

    zip_path = get_bundle_zip_path(bundle_id)
    if zip_path is None:
        raise HTTPException(status_code=404, detail="Bundle zip file not found")

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=f"avni-bundle-{bundle_id[:8]}.zip",
    )


@router.post("/bundle/generate-from-excel", response_model=BundleStatus)
async def generate_from_excel(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> BundleStatus:
    """Upload one or more SRS Excel files (.xlsx) and generate a bundle.

    Supports uploading scoping doc + modelling doc together.
    Parses and merges files into structured SRSData, then triggers
    bundle generation in the background.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    # Validate and save all files
    tmp_paths: list[str] = []
    filenames: list[str] = []
    try:
        for file in files:
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")
            if not file.filename.endswith((".xlsx", ".xls")):
                raise HTTPException(
                    status_code=400,
                    detail=f"File must be an Excel file (.xlsx or .xls): {file.filename}",
                )
            suffix = os.path.splitext(file.filename)[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_paths.append(tmp.name)
                filenames.append(file.filename)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded files: {str(e)}")

    bundle_id = str(uuid.uuid4())

    # Parse the Excel files (merge if multiple)
    try:
        if len(tmp_paths) == 1:
            srs_data = parse_srs_excel(tmp_paths[0])
        else:
            srs_data = parse_multiple_srs_excels(tmp_paths)
    except Exception as e:
        for p in tmp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        logger.exception("Failed to parse SRS Excel files: %s", filenames)
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse SRS Excel files: {str(e)}",
        )

    # Clean up temp files
    for p in tmp_paths:
        try:
            os.unlink(p)
        except OSError:
            pass

    # Validate minimum viable SRS
    if not srs_data.forms:
        raise HTTPException(
            status_code=422,
            detail="SRS Excel files did not contain any parseable form definitions. "
                   "Ensure the files have sheets with 'Field Name' and 'Data Type' columns.",
        )

    logger.info(
        "Parsed SRS Excel %s: %d forms, %d encounter types, %d programs",
        filenames,
        len(srs_data.forms),
        len(srs_data.encounterTypes),
        len(srs_data.programs),
    )

    # Start generation in background
    status = BundleStatus(
        id=bundle_id,
        status=BundleStatusType.PENDING,
        progress=0,
        message=f"SRS parsed from '{file.filename}'. Bundle generation queued.",
    )

    background_tasks.add_task(_run_generation, srs_data, bundle_id)

    return status


@router.post("/bundle/parse-excel")
async def parse_excel(file: UploadFile = File(...)) -> dict:
    """Parse an SRS Excel file and return the structured SRSData as JSON.

    This is a preview/debug endpoint that lets you see what the parser
    extracts from the Excel file without generating a bundle.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(
            status_code=400,
            detail="File must be an Excel file (.xlsx or .xls)",
        )

    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save uploaded file: {str(e)}",
        )

    try:
        srs_data = parse_srs_excel(tmp_path)
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        logger.exception("Failed to parse SRS Excel file: %s", file.filename)
        raise HTTPException(
            status_code=422,
            detail=f"Failed to parse SRS Excel file: {str(e)}",
        )

    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    total_fields = sum(
        len(field)
        for form in srs_data.forms
        for field in [
            [f for g in form.groups for f in g.fields]
        ]
    )

    return {
        "parsed_srs": srs_data.model_dump(exclude_none=True),
        "summary": {
            "organization": srs_data.orgName,
            "forms_count": len(srs_data.forms),
            "total_fields": total_fields,
            "programs": [p.get("name", p) if isinstance(p, dict) else p for p in srs_data.programs],
            "encounter_types": srs_data.encounterTypes,
            "groups": srs_data.groups,
            "subject_types": [st.get("name", "") for st in srs_data.subjectTypes],
        },
    }


# ─── SRS Template Download ────────────────────────────────────────────────────


@router.get("/bundle/srs-template")
async def download_srs_template(
    format: str = Query(default="xlsx", description="Template format: 'xlsx' or 'csv'"),
) -> Response:
    """Download the canonical SRS template.

    The canonical template has a fixed structure that maps 1:1 to Avni's data model.
    Fill it in and upload via /bundle/generate-from-excel for 100% correct bundles.
    """
    from app.services.canonical_srs_template import generate_template_xlsx, generate_template_csv

    if format == "csv":
        content = generate_template_csv()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=avni-srs-template.csv"},
        )

    content = generate_template_xlsx()
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=avni-srs-template.xlsx"},
    )


@router.get("/bundle/srs-review/{session_id}/template")
async def download_review_template(session_id: str) -> Response:
    """Download the parsed SRS as a filled canonical template XLSX.

    Enables the self-correcting loop:
    Upload free-form → parse → download canonical → edit in Excel → re-upload → 100% correct.
    """
    from app.services.canonical_srs_template import generate_filled_template
    from app.services.context_manager import _bundle_pending

    pending = _bundle_pending.get(session_id)
    if not pending or not pending.get("srs_data"):
        raise HTTPException(
            status_code=404,
            detail="No parsed SRS data found for this session. Upload an SRS file first.",
        )

    srs_data = pending["srs_data"]
    content = generate_filled_template(srs_data)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=avni-srs-review.xlsx"},
    )


@router.post("/bundle/export-canonical")
async def export_canonical_template(request: BundleGenerateRequest) -> Response:
    """Export existing SRS data as a filled canonical template XLSX.

    Enables round-tripping: upload free-form → parse → download canonical → edit → re-upload.
    """
    from app.services.canonical_srs_template import generate_filled_template

    if not request.srs_data:
        raise HTTPException(status_code=400, detail="srs_data is required")

    content = generate_filled_template(request.srs_data)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=avni-srs-canonical.xlsx"},
    )


# ─── Clarity Analysis ─────────────────────────────────────────────────────────


class ClarityAnalysisRequest(BaseModel):
    """Request body for clarity analysis."""
    srs_data: dict = Field(description="SRSData as a JSON dict")
    org_name: str | None = Field(default=None, description="Organisation name for context")
    sector: str | None = Field(default=None, description="Sector for context-aware suggestions")


class ClarityQuestionResponse(BaseModel):
    """A single clarity question in the API response."""
    id: str
    category: str
    severity: str
    question: str
    context: str
    suggestions: list[str] = Field(default_factory=list)
    default: str | None = None
    field_path: str | None = None


class ClarityAnalysisResponse(BaseModel):
    """Response from clarity analysis."""
    questions: list[ClarityQuestionResponse]
    can_proceed: bool = Field(description="True if no unanswered CRITICAL questions remain")
    critical_count: int = 0
    important_count: int = 0
    nice_count: int = 0
    formatted_message: str = Field(default="", description="Pre-formatted chat message")


@router.post("/bundle/analyze-clarity", response_model=ClarityAnalysisResponse)
async def analyze_clarity(request: ClarityAnalysisRequest) -> ClarityAnalysisResponse:
    """Analyze SRS data for gaps and return targeted clarification questions.

    Run this before bundle generation to detect missing entities, ambiguous
    concepts, incomplete rules, unclear schedules, and conflicting info.
    Only CRITICAL questions must be answered before generation can proceed.
    """
    from app.services.clarity_engine import clarity_engine

    org_ctx = {}
    if request.org_name:
        org_ctx["org_name"] = request.org_name
    if request.sector:
        org_ctx["sector"] = request.sector

    questions = await clarity_engine.analyze(
        request.srs_data,
        org_context=org_ctx or None,
    )

    response_questions = [
        ClarityQuestionResponse(
            id=q.id,
            category=q.category.value,
            severity=q.severity.value,
            question=q.question,
            context=q.context,
            suggestions=q.suggestions,
            default=q.default,
            field_path=q.field_path,
        )
        for q in questions
    ]

    return ClarityAnalysisResponse(
        questions=response_questions,
        can_proceed=clarity_engine.can_proceed(questions),
        critical_count=sum(1 for q in questions if q.severity.value == "critical"),
        important_count=sum(1 for q in questions if q.severity.value == "important"),
        nice_count=sum(1 for q in questions if q.severity.value == "nice"),
        formatted_message=clarity_engine.format_for_chat(questions),
    )


class ClarityApplyRequest(BaseModel):
    """Request to apply clarity answers to SRS data."""
    srs_data: dict = Field(description="Original SRSData as a JSON dict")
    answers: dict[str, str] = Field(description="Mapping of question ID -> user answer")


@router.post("/bundle/apply-clarity")
async def apply_clarity(request: ClarityApplyRequest) -> dict:
    """Apply user's answers to clarity questions and return patched SRS data.

    The patched SRS data will have a `_clarity_answers` key with the raw
    answers, which the LLM can use during bundle generation to fill gaps.
    """
    from app.services.clarity_engine import clarity_engine

    patched = clarity_engine.apply_answers(request.srs_data, request.answers)
    return {"srs_data": patched, "answers_applied": len(request.answers)}


# ─── AI Auto-Fill ─────────────────────────────────────────────────────────────

AI_AUTOFILL_SYSTEM_PROMPT = """You are an expert Avni implementation consultant helping fill in an SRS (Scoping & Requirement Specification) document.

Given the current tab data and context, suggest realistic values for any empty or incomplete fields.
Return ONLY a JSON object with the suggested values. Use the same field names/keys as the input data.

Rules:
1. Only suggest values for fields that are empty, blank, or zero.
2. Keep suggestions realistic and appropriate for Indian NGO field programs.
3. For form fields, suggest appropriate data types, validation rules, and options.
4. For visit scheduling, suggest realistic frequencies and conditions.
5. For dashboard cards, suggest actionable card names with clear filter logic.
6. Do NOT change any fields that already have values.
7. Return valid JSON only, no markdown or explanations."""


@router.post("/bundle/ai-autofill")
async def ai_autofill(request: dict) -> dict:
    """Use Claude to suggest values for empty SRS fields.

    Body: {
        "tab": "programs"|"users"|"w3h"|"forms"|"scheduling"|"dashboard"|"permissions",
        "current_data": dict,
        "context": str
    }
    Returns: suggested values for empty fields.
    """
    tab = request.get("tab", "")
    current_data = request.get("current_data", {})
    context = request.get("context", "")

    if not tab:
        raise HTTPException(status_code=400, detail="'tab' is required")

    user_message = (
        f"SRS Tab: {tab}\n\n"
        f"Context: {context}\n\n"
        f"Current data (fill in empty fields only):\n{json.dumps(current_data, indent=2, default=str)}"
    )

    try:
        response_text = await claude_client.complete(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=AI_AUTOFILL_SYSTEM_PROMPT,
        )

        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        suggestions = json.loads(cleaned)
        return {"tab": tab, "suggestions": suggestions}

    except json.JSONDecodeError as e:
        logger.warning("AI autofill returned non-JSON for tab '%s': %s", tab, str(e))
        raise HTTPException(
            status_code=422,
            detail=f"AI response could not be parsed as JSON: {str(e)}",
        )
    except Exception as e:
        logger.exception("AI autofill failed for tab '%s'", tab)
        raise HTTPException(
            status_code=500,
            detail=f"AI autofill failed: {str(e)}",
        )


# ─── Bundle Locking ──────────────────────────────────────────────────────────

class LockRequest(BaseModel):
    user_id: str = Field(..., description="ID of the user requesting the lock")
    ttl_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        description="Lock duration in seconds (30–3600, default 300)",
    )


class UnlockRequest(BaseModel):
    user_id: str = Field(..., description="ID of the user releasing the lock")


@router.post("/bundle/{bundle_id}/lock")
async def lock_bundle(bundle_id: str, request: LockRequest) -> dict:
    """Acquire an exclusive edit lock on a bundle.

    The lock prevents other users from editing the bundle until it expires
    or is explicitly released. If the lock is already held by this user,
    it is refreshed with a new TTL.
    """
    acquired = await acquire_bundle_lock(
        bundle_id, request.user_id, request.ttl_seconds
    )
    if not acquired:
        existing = await get_bundle_lock(bundle_id)
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Bundle is locked by another user",
                "locked_by": existing["locked_by"] if existing else "unknown",
                "expires_at": existing["expires_at"].isoformat() if existing else None,
            },
        )
    lock = await get_bundle_lock(bundle_id)
    return {
        "bundle_id": bundle_id,
        "locked": True,
        "locked_by": lock["locked_by"] if lock else request.user_id,
        "expires_at": lock["expires_at"].isoformat() if lock else None,
    }


@router.delete("/bundle/{bundle_id}/lock")
async def unlock_bundle(bundle_id: str, request: UnlockRequest) -> dict:
    """Release an edit lock on a bundle. Only the lock owner can release it."""
    released = await release_bundle_lock(bundle_id, request.user_id)
    if not released:
        existing = await get_bundle_lock(bundle_id)
        if existing is None:
            return {"bundle_id": bundle_id, "locked": False, "message": "No active lock"}
        raise HTTPException(
            status_code=403,
            detail="You do not own this lock",
        )
    return {"bundle_id": bundle_id, "locked": False, "message": "Lock released"}


@router.get("/bundle/{bundle_id}/lock")
async def check_bundle_lock(bundle_id: str) -> dict:
    """Check the current lock status of a bundle."""
    lock = await get_bundle_lock(bundle_id)
    if lock is None:
        return {"bundle_id": bundle_id, "locked": False}
    return {
        "bundle_id": bundle_id,
        "locked": True,
        "locked_by": lock["locked_by"],
        "locked_at": lock["locked_at"].isoformat(),
        "expires_at": lock["expires_at"].isoformat(),
    }


@router.post("/bundle/locks/cleanup")
async def cleanup_locks() -> dict:
    """Remove all expired bundle locks (admin housekeeping)."""
    count = await cleanup_expired_locks()
    return {"expired_locks_removed": count}


# ─── SRS Quality Validation ──────────────────────────────────────────────────

class SRSValidationIssue(BaseModel):
    severity: str = Field(description="'error', 'warning', or 'info'")
    category: str = Field(description="Category: 'missing_data', 'ambiguous', 'inconsistent', 'incomplete'")
    message: str = Field(description="Human-readable description of the issue")
    field: str | None = Field(default=None, description="Affected field/form name")
    suggestion: str | None = Field(default=None, description="Suggested fix")


def _validate_srs_quality(srs_data: SRSData) -> list[dict]:
    """Run deterministic quality checks on parsed SRS data.

    Returns a list of issues with severity, category, message, and suggestions.
    """
    issues: list[dict] = []

    # No forms parsed
    if not srs_data.forms:
        issues.append({
            "severity": "error",
            "category": "missing_data",
            "message": "No forms were parsed from the SRS. The Excel file may be missing 'Field Name' and 'Data Type' columns.",
            "suggestion": "Ensure each form sheet has columns named 'Field Name' and 'Data Type'.",
        })
        return issues

    # Check each form
    for form in srs_data.forms:
        total_fields = sum(len(g.fields) for g in form.groups)

        # Empty forms
        if total_fields == 0:
            issues.append({
                "severity": "warning",
                "category": "missing_data",
                "message": f"Form '{form.name}' has no fields.",
                "field": form.name,
                "suggestion": "Add fields to this form or remove the sheet if it's not needed.",
            })
            continue

        # Form type not classified
        if form.formType == "Encounter" and not form.encounterTypeName:
            issues.append({
                "severity": "warning",
                "category": "ambiguous",
                "message": f"Form '{form.name}' is classified as Encounter but has no encounter type name.",
                "field": form.name,
                "suggestion": f"Is '{form.name}' a general encounter or a program encounter? Specify which program it belongs to.",
            })

        # Fields with unknown data types
        for group in form.groups:
            for field in group.fields:
                if field.dataType == "NA" or not field.dataType:
                    issues.append({
                        "severity": "warning",
                        "category": "ambiguous",
                        "message": f"Field '{field.name}' in form '{form.name}' has unknown data type.",
                        "field": field.name,
                        "suggestion": f"What type should '{field.name}' be? (Text, Numeric, Date, Coded/SingleSelect, Coded/MultiSelect, Notes, Image, etc.)",
                    })

                # Coded fields without options
                if field.dataType == "Coded" and not field.options:
                    issues.append({
                        "severity": "warning",
                        "category": "incomplete",
                        "message": f"Field '{field.name}' in form '{form.name}' is Coded but has no options listed.",
                        "field": field.name,
                        "suggestion": f"What are the possible values for '{field.name}'?",
                    })

                # Numeric without range
                if field.dataType == "Numeric" and field.lowAbsolute is None and field.highAbsolute is None:
                    issues.append({
                        "severity": "info",
                        "category": "incomplete",
                        "message": f"Numeric field '{field.name}' in form '{form.name}' has no validation range.",
                        "field": field.name,
                        "suggestion": f"Should '{field.name}' have min/max validation? (e.g., weight: 0-200 kg)",
                    })

                # Skip logic that couldn't be parsed
                if field.keyValues:
                    for kv in field.keyValues:
                        if kv.get("key") in ("showWhen", "hideWhen"):
                            val = str(kv.get("value", ""))
                            if val.startswith("UNPARSED:"):
                                issues.append({
                                    "severity": "warning",
                                    "category": "ambiguous",
                                    "message": f"Skip logic for '{field.name}' in form '{form.name}' could not be parsed: {val[9:]}",
                                    "field": field.name,
                                    "suggestion": f"Please rephrase the condition for when '{field.name}' should be shown/hidden.",
                                })

    # No programs but has enrollment forms
    has_enrolment = any(f.formType == "ProgramEnrolment" for f in srs_data.forms)
    if has_enrolment and not srs_data.programs:
        issues.append({
            "severity": "error",
            "category": "inconsistent",
            "message": "Enrollment forms found but no programs defined.",
            "suggestion": "Which programs do these enrollment forms belong to?",
        })

    # Programs without any encounter types
    if srs_data.programs:
        programs_with_encounters = set()
        for f in srs_data.forms:
            if f.formType in ("ProgramEncounter", "ProgramEncounterCancellation") and f.programName:
                programs_with_encounters.add(f.programName)
        for p in srs_data.programs:
            pname = p.get("name", p) if isinstance(p, dict) else p
            if pname not in programs_with_encounters:
                issues.append({
                    "severity": "info",
                    "category": "incomplete",
                    "message": f"Program '{pname}' has no encounter forms linked to it.",
                    "field": pname,
                    "suggestion": f"What encounters/visits should be scheduled under program '{pname}'?",
                })

    # No visit scheduling data
    if not srs_data.visitSchedules and any(
        f.formType in ("ProgramEncounter", "Encounter") for f in srs_data.forms
    ):
        issues.append({
            "severity": "info",
            "category": "incomplete",
            "message": "No visit scheduling data found. Visit schedules will use default intervals.",
            "suggestion": "Add a 'Visit Scheduling' sheet with columns: Trigger Form, Schedule Form, Due Days, Overdue Days.",
        })

    return issues


@router.post("/bundle/validate-srs")
async def validate_srs(file: UploadFile = File(...)) -> dict:
    """Parse an SRS Excel file and return quality issues + follow-up questions.

    Returns the parsed SRS data along with a list of issues that need
    clarification before bundle generation. Issues include missing data,
    ambiguous field types, unparsed skip logic, and inconsistencies.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="File must be .xlsx or .xls")

    try:
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    try:
        srs_data = parse_srs_excel(tmp_path)
    except Exception as e:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=422, detail=f"Failed to parse SRS: {e}")

    try:
        os.unlink(tmp_path)
    except OSError:
        pass

    issues = _validate_srs_quality(srs_data)

    errors = [i for i in issues if i["severity"] == "error"]
    warnings = [i for i in issues if i["severity"] == "warning"]
    infos = [i for i in issues if i["severity"] == "info"]

    # Generate follow-up questions from issues
    questions = []
    for issue in issues:
        if issue.get("suggestion") and issue["severity"] in ("error", "warning"):
            questions.append({
                "question": issue["suggestion"],
                "context": issue["message"],
                "field": issue.get("field"),
            })

    total_fields = sum(
        len(f) for form in srs_data.forms for f in [[f for g in form.groups for f in g.fields]]
    )

    return {
        "parsed_srs": srs_data.model_dump(exclude_none=True),
        "summary": {
            "organization": srs_data.orgName,
            "forms_count": len(srs_data.forms),
            "total_fields": total_fields,
            "programs": [p.get("name", p) if isinstance(p, dict) else p for p in srs_data.programs],
            "encounter_types": srs_data.encounterTypes,
        },
        "quality": {
            "errors": len(errors),
            "warnings": len(warnings),
            "info": len(infos),
            "issues": issues,
            "follow_up_questions": questions,
            "ready_for_generation": len(errors) == 0,
        },
    }


# ─── Bundle Correction (NL → re-generate) ───────────────────────────────────

BUNDLE_CORRECTION_SYSTEM_PROMPT = """You are an expert Avni implementation engineer applying a targeted correction to an SRS bundle.

## AVNI DATA MODEL (CRITICAL — understand before making changes):
- **SubjectType**: The entity being registered (e.g., Individual, Household, Family). Has a REGISTRATION form (formType=IndividualProfile).
- **Program**: A longitudinal program a subject is ENROLLED in (e.g., Maternal Health, Institution). Has an ENROLMENT form (formType=ProgramEnrolment) and an EXIT form (formType=ProgramExit).
- **EncounterType**: A visit/interaction within a program (e.g., ANC Visit, Daily Attendance, Baseline Assessment). Has a FORM (formType=ProgramEncounter if under a program, or formType=Encounter if standalone).
- **ProgramEnrolment form**: The form filled when enrolling a subject into a program. It is NOT a separate program — it belongs to the program.

## COMMON MISTAKES TO AVOID:
- "X Enrolment" is usually the ENROLMENT FORM for program "X", NOT a separate program.
- When user says "X is a program, not an encounter type": move X from encounterTypes to programs, change its form's formType from ProgramEncounter to ProgramEnrolment, and set form.programName = X.
- When moving something between programs/encounterTypes: update ALL related forms' formType, programName, and encounterTypeName fields consistently.
- NEVER drop existing forms, fields, programs, or encounter types unless explicitly asked.
- NEVER invent new forms or fields that weren't in the original. Only modify what the user asks.

## RULES:
1. Return ONLY the modified SRS JSON. No explanations, no markdown.
2. PRESERVE all existing data — forms, fields, options, groups — unless the correction specifically changes them. Count forms before and after: the count should only change if the user explicitly asked to add or remove forms.
3. Handle these correction types:
   - Move entity between programs/encounterTypes: update ALL references (forms, mappings)
   - Change form type: update formType AND programName/encounterTypeName consistently
   - Add/remove fields: modify the specific form's groups.fields
   - Change data types, options, skip logic, visit schedules
   - Rename forms/fields/programs/encounter types
4. Return valid JSON matching the SRSData schema.
5. Add a "_correction_notes" field explaining exactly what you changed and what you preserved."""


class BundleCorrectionRequest(BaseModel):
    bundle_id: str = Field(description="ID of the bundle to correct")
    correction: str = Field(description="Natural language correction instruction")
    srs_data: dict | None = Field(default=None, description="Current SRS data (if not stored)")


@router.post("/bundle/correct")
async def correct_bundle(
    background_tasks: BackgroundTasks,
    request: BundleCorrectionRequest,
) -> dict:
    """Apply a natural language correction to a bundle and regenerate it.

    Takes a correction like "ANC should be monthly not weekly" or
    "add skip logic for weight field when age < 18" and uses LLM
    to modify the SRS data, then regenerates the bundle.

    Returns the new bundle ID for tracking regeneration progress.
    """
    from app.services.feedback import feedback_service

    # Get existing SRS data from pending bundle or from request
    srs_dict = request.srs_data
    if not srs_dict:
        pending = feedback_service.get_pending_bundle(request.bundle_id)
        if pending and "srs_data" in pending:
            srs_dict = pending["srs_data"]

    if not srs_dict:
        raise HTTPException(
            status_code=404,
            detail="Bundle SRS data not found. Provide srs_data in the request or ensure the bundle exists.",
        )

    # Use LLM to apply the correction to the SRS data
    try:
        correction_prompt = (
            f"Current SRS data:\n```json\n{json.dumps(srs_dict, indent=2)}\n```\n\n"
            f"User's correction:\n{request.correction}\n\n"
            f"Apply this correction and return the modified SRS JSON."
        )

        result = await claude_client.complete(
            messages=[{"role": "user", "content": correction_prompt}],
            system_prompt=BUNDLE_CORRECTION_SYSTEM_PROMPT,
        )

        # Extract JSON from LLM response
        modified_srs = _extract_json_from_response(result)
        if not modified_srs:
            raise ValueError("LLM did not return valid JSON")

    except Exception as e:
        logger.exception("Failed to apply correction: %s", request.correction)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply correction: {str(e)}",
        )

    # Extract correction notes if any
    correction_notes = modified_srs.pop("_correction_notes", None)

    # Parse into SRSData
    try:
        corrected_srs = SRSData(**modified_srs)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail=f"Corrected SRS data is invalid: {str(e)}. LLM may have produced malformed output.",
        )

    # Generate new bundle
    new_bundle_id = str(uuid.uuid4())
    status = BundleStatus(
        id=new_bundle_id,
        status=BundleStatusType.PENDING,
        progress=0,
        message=f"Applying correction: {request.correction[:100]}...",
    )

    background_tasks.add_task(_run_generation, corrected_srs, new_bundle_id)

    # Index the correction for future learning
    try:
        await feedback_service.save_feedback(
            session_id=request.bundle_id,
            message_id=new_bundle_id,
            rating="correction",
            correction=request.correction,
            metadata={
                "type": "bundle_correction",
                "original_bundle_id": request.bundle_id,
                "new_bundle_id": new_bundle_id,
            },
        )
    except Exception:
        logger.warning("Failed to save correction feedback")

    return {
        "original_bundle_id": request.bundle_id,
        "new_bundle_id": new_bundle_id,
        "correction_applied": request.correction,
        "correction_notes": correction_notes,
        "status": status.model_dump(),
    }


def _extract_json_from_response(text: str) -> dict | None:
    """Extract JSON object from LLM response that may contain markdown fences."""
    # Try direct parse first
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from code fences
    import re
    patterns = [
        r"```json\s*\n(.*?)\n```",
        r"```\s*\n(.*?)\n```",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                continue

    # Last resort: find first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def verify_bundle_lock_ownership(bundle_id: str, user_id: str) -> None:
    """Raise HTTPException(409) if the bundle is locked by someone else.

    Call this at the top of any edit endpoint. If no lock exists the edit
    is allowed (optimistic — locking is opt-in). If a lock exists but is
    owned by *this* user, the edit proceeds.
    """
    lock = await get_bundle_lock(bundle_id)
    if lock and lock["locked_by"] != user_id:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Bundle is locked by another user",
                "locked_by": lock["locked_by"],
                "expires_at": lock["expires_at"].isoformat(),
            },
        )
