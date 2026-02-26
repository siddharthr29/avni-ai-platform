import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse

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

logger = logging.getLogger(__name__)

router = APIRouter()

SRS_PARSE_SYSTEM_PROMPT = """You are an expert at parsing Avni SRS (Scoping & Requirement Specification) documents into structured JSON.

Given a text description of an Avni implementation, extract and structure it into this exact JSON format:

{
  "orgName": "Organisation Name",
  "subjectTypes": [{"name": "Individual", "type": "Person"}],
  "programs": [{"name": "Program Name", "colour": "#E91E63"}],
  "encounterTypes": ["Encounter Type 1", "Encounter Type 2"],
  "forms": [
    {
      "name": "Form Name",
      "formType": "IndividualProfile|ProgramEnrolment|ProgramExit|ProgramEncounter|ProgramEncounterCancellation|Encounter|IndividualEncounterCancellation",
      "programName": "Program Name or null",
      "encounterTypeName": "Encounter Type Name or null",
      "groups": [
        {
          "name": "Group Name",
          "fields": [
            {
              "name": "Field Name",
              "dataType": "Text|Numeric|Date|Coded|Notes|Time|Image",
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
  "groups": ["Everyone", "Admin", "Supervisor"],
  "addressLevelTypes": [
    {"name": "State", "level": 3},
    {"name": "District", "level": 2, "parent": "State"},
    {"name": "Block", "level": 1, "parent": "District"}
  ],
  "programEncounterMappings": [
    {"program": "Program Name", "encounterTypes": ["Encounter Type 1"]}
  ],
  "generalEncounterTypes": ["General Encounter"]
}

Rules:
1. Include ALL forms: registration, program enrolment, exit, encounters, and cancellation forms.
2. For each encounter type, generate both the encounter form and its cancellation form.
3. Cancellation forms should have fields: Cancellation Reason (Coded: Unavailable, Migrated, Refused, Other) and Other Reason (Text, optional).
4. ProgramEnrolment forms have formType "ProgramEnrolment" and need programName set.
5. ProgramExit forms have formType "ProgramExit" and need programName set.
6. ProgramEncounter forms need both programName and encounterTypeName.
7. Always include an "Everyone" group.
8. Infer programEncounterMappings from the forms.
9. For Coded fields, always include the list of options.
10. For Numeric fields, include unit if applicable.

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


async def _run_generation(srs_data: SRSData, bundle_id: str) -> None:
    """Background task to run bundle generation."""
    try:
        await generate_from_srs(srs_data, bundle_id)
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
