"""Document extraction and structuring endpoints — Phase 2 concept note processing.

Provides:
- POST /document/extract   — Upload PDF/text, get structured requirements
- POST /document/map       — Map structured requirements to Avni domain model
- POST /document/clarify   — Get clarification questions for requirements
- POST /document/process   — Full pipeline: extract → structure → map → clarify
"""

import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.models.schemas import SRSData
from app.services.document_extractor import (
    ClarificationQuestion,
    ExtractedDocument,
    StructuredRequirements,
    extract_from_pdf,
    extract_from_text,
    generate_clarifications,
    map_to_avni_domain,
    process_document,
    structure_content,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ExtractRequest(BaseModel):
    """Request for text-only extraction (PDF uses multipart upload)."""
    text: str = Field(description="Raw text content (call notes, plain text requirements)")
    title: str = Field(default="Untitled", description="Document title")


class ExtractResponse(BaseModel):
    text: str
    tables: list[list[list[str]]]
    metadata: dict[str, str]
    requirements: dict[str, Any]


class MapRequest(BaseModel):
    """Request to map structured requirements to Avni domain model."""
    requirements: dict[str, Any] = Field(description="Structured requirements (from /document/extract)")
    org_name: str = Field(default="Organisation", description="Organisation name for the SRS")


class MapResponse(BaseModel):
    srs_data: dict[str, Any]


class ClarifyRequest(BaseModel):
    """Request to generate clarification questions."""
    requirements: dict[str, Any] = Field(description="Structured requirements")
    srs_data: dict[str, Any] = Field(description="Mapped SRS data (from /document/map)")


class ClarifyResponse(BaseModel):
    questions: list[dict[str, Any]]


class ProcessRequest(BaseModel):
    """Request for the full processing pipeline (text input)."""
    text: str = Field(description="Raw text content")
    title: str = Field(default="Untitled")
    org_name: str = Field(default="Organisation")


class ProcessResponse(BaseModel):
    extracted: dict[str, Any]
    requirements: dict[str, Any]
    srs_data: dict[str, Any]
    clarifications: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Helper: dict → dataclass conversions
# ---------------------------------------------------------------------------

def _dict_to_requirements(data: dict[str, Any]) -> StructuredRequirements:
    """Convert a dict (from JSON request) back to StructuredRequirements."""
    return StructuredRequirements(
        title=data.get("title", ""),
        subject_types=data.get("subject_types", []),
        programs=data.get("programs", []),
        encounter_types=data.get("encounter_types", []),
        data_fields=data.get("data_fields", []),
        visit_schedules=data.get("visit_schedules", []),
        rules=data.get("rules", []),
        ambiguities=data.get("ambiguities", []),
    )


def _requirements_to_dict(req: StructuredRequirements) -> dict[str, Any]:
    """Serialize StructuredRequirements to a dict for JSON response."""
    return {
        "title": req.title,
        "subject_types": req.subject_types,
        "programs": req.programs,
        "encounter_types": req.encounter_types,
        "data_fields": req.data_fields,
        "visit_schedules": req.visit_schedules,
        "rules": req.rules,
        "ambiguities": req.ambiguities,
    }


def _clarification_to_dict(q: ClarificationQuestion) -> dict[str, Any]:
    """Serialize a ClarificationQuestion to a dict."""
    result: dict[str, Any] = {
        "question": q.question,
        "context": q.context,
    }
    if q.options is not None:
        result["options"] = q.options
    if q.field is not None:
        result["field"] = q.field
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/document/extract", response_model=ExtractResponse)
async def extract_document(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    title: str = Form(default="Untitled"),
):
    """Extract and structure content from a PDF file or plain text.

    Provide either a PDF file upload OR text content (not both).
    Returns extracted text, tables, metadata, and structured requirements.
    """
    if file and text:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or text content, not both",
        )

    if not file and not text:
        raise HTTPException(
            status_code=400,
            detail="Either a file upload or text content is required",
        )

    try:
        if file:
            # Validate file type
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")

            ext = os.path.splitext(file.filename)[1].lower()
            if ext != ".pdf":
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {ext}. Only .pdf is supported for file upload. Use text field for plain text.",
                )

            # Save to temp file and extract
            content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                extracted = await extract_from_pdf(tmp_path)
            finally:
                os.unlink(tmp_path)
        else:
            extracted = await extract_from_text(text, title=title)

        # Structure the content
        full_text = extracted.text
        if extracted.tables:
            table_texts = []
            for i, table in enumerate(extracted.tables, 1):
                rows = [" | ".join(row) for row in table]
                table_texts.append(f"\n[Table {i}]\n" + "\n".join(rows))
            full_text += "\n\n--- Extracted Tables ---" + "".join(table_texts)

        requirements = await structure_content(full_text)
        if not requirements.title and extracted.metadata.get("title"):
            requirements.title = extracted.metadata["title"]

        return ExtractResponse(
            text=extracted.text,
            tables=extracted.tables,
            metadata=extracted.metadata,
            requirements=_requirements_to_dict(requirements),
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Document extraction failed")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.post("/document/map", response_model=MapResponse)
async def map_requirements(request: MapRequest):
    """Map structured requirements to the Avni domain model (SRSData).

    Takes the structured requirements output from /document/extract and
    produces an SRSData JSON suitable for bundle generation.
    """
    try:
        requirements = _dict_to_requirements(request.requirements)
        srs_data = await map_to_avni_domain(requirements, org_name=request.org_name)
        return MapResponse(srs_data=srs_data.model_dump())

    except Exception as e:
        logger.exception("Domain mapping failed")
        raise HTTPException(status_code=500, detail=f"Mapping failed: {str(e)}")


@router.post("/document/clarify", response_model=ClarifyResponse)
async def clarify_requirements(request: ClarifyRequest):
    """Generate targeted clarification questions for ambiguous requirements.

    Takes both the structured requirements and mapped SRSData to identify
    gaps, inconsistencies, and missing information.
    """
    try:
        requirements = _dict_to_requirements(request.requirements)
        srs_data = SRSData(**request.srs_data)
        questions = await generate_clarifications(requirements, srs_data)
        return ClarifyResponse(
            questions=[_clarification_to_dict(q) for q in questions]
        )

    except Exception as e:
        logger.exception("Clarification generation failed")
        raise HTTPException(status_code=500, detail=f"Clarification failed: {str(e)}")


@router.post("/document/process", response_model=ProcessResponse)
async def process_full_pipeline(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    title: str = Form(default="Untitled"),
    org_name: str = Form(default="Organisation"),
):
    """Run the full document processing pipeline: extract → structure → map → clarify.

    Accepts either a PDF file or plain text. Returns the complete result
    including extracted text, structured requirements, SRSData, and
    clarification questions.
    """
    if file and text:
        raise HTTPException(
            status_code=400,
            detail="Provide either a file upload or text content, not both",
        )

    if not file and not text:
        raise HTTPException(
            status_code=400,
            detail="Either a file upload or text content is required",
        )

    try:
        tmp_path = None

        if file:
            if not file.filename:
                raise HTTPException(status_code=400, detail="No filename provided")

            ext = os.path.splitext(file.filename)[1].lower()
            if ext != ".pdf":
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {ext}. Only .pdf is supported.",
                )

            content = await file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(content)
                tmp_path = tmp.name

        try:
            result = await process_document(
                file_path=tmp_path,
                raw_text=text,
                title=title,
                org_name=org_name,
            )
        finally:
            if tmp_path:
                os.unlink(tmp_path)

        return ProcessResponse(
            extracted={
                "text": result.extracted.text,
                "tables": result.extracted.tables,
                "metadata": result.extracted.metadata,
            },
            requirements=_requirements_to_dict(result.requirements),
            srs_data=result.srs_data.model_dump(),
            clarifications=[_clarification_to_dict(q) for q in result.clarifications],
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Full pipeline processing failed")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
