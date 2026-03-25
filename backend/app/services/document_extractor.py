"""Document extractor service — Phase 2 of concept note processing.

Extracts structured specs from unstructured documents (PDFs, plain text,
call notes) and maps them to the Avni domain model. The existing SRS parser
only handles structured Excel files; this service handles everything else.

Pipeline: extract → structure → map → clarify
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.models.schemas import SRSData, SRSFormDefinition, SRSFormField, SRSFormGroup
from app.services.claude_client import claude_client
from app.services.rag.fallback import rag_service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ExtractedDocument:
    """Raw content extracted from a PDF or text document."""

    text: str
    tables: list[list[list[str]]] = field(default_factory=list)  # list of tables, each is rows of cells
    metadata: dict[str, str] = field(default_factory=dict)  # title, pages, source, etc.


@dataclass
class StructuredRequirements:
    """Semi-structured representation of requirements parsed from raw text."""

    title: str = ""
    subject_types: list[str] = field(default_factory=list)  # "Individual", "Household"
    programs: list[str] = field(default_factory=list)  # "Maternal Health", "Nutrition"
    encounter_types: list[dict[str, str]] = field(default_factory=list)
    # e.g. {"name": "ANC Visit", "program": "Maternal Health", "frequency": "monthly"}
    data_fields: list[dict[str, str]] = field(default_factory=list)
    # e.g. {"name": "Weight", "type": "Numeric", "form": "ANC Visit", "section": "Vitals"}
    visit_schedules: list[str] = field(default_factory=list)  # raw text about scheduling
    rules: list[str] = field(default_factory=list)  # raw text about conditions/logic
    ambiguities: list[str] = field(default_factory=list)  # unclear parts


@dataclass
class ClarificationQuestion:
    """A targeted question about an ambiguous requirement."""

    question: str
    context: str  # what triggered this question
    options: list[str] | None = None  # suggested answers
    field: str | None = None  # which field/entity this relates to


# ---------------------------------------------------------------------------
# PDF extraction (graceful degradation across libraries)
# ---------------------------------------------------------------------------

def _extract_with_pymupdf(file_path: str) -> ExtractedDocument:
    """Extract using PyMuPDF (fitz) — best quality, already in requirements."""
    import fitz  # pymupdf

    doc = fitz.open(file_path)
    pages_text: list[str] = []
    all_tables: list[list[list[str]]] = []

    for page_num, page in enumerate(doc, 1):
        text = page.get_text("text")
        if text.strip():
            pages_text.append(text)

        # Extract tables via PyMuPDF's built-in table finder (v1.23+)
        try:
            tables = page.find_tables()
            for table in tables:
                extracted = table.extract()
                if extracted:
                    # Clean None cells
                    cleaned = [
                        [str(cell) if cell is not None else "" for cell in row]
                        for row in extracted
                    ]
                    all_tables.append(cleaned)
        except (AttributeError, Exception):
            # Older pymupdf version without find_tables — skip table extraction
            pass

    full_text = "\n\n".join(pages_text)
    metadata = {
        "title": doc.metadata.get("title", "") or os.path.basename(file_path),
        "pages": str(doc.page_count),
        "source": os.path.basename(file_path),
        "author": doc.metadata.get("author", ""),
    }
    doc.close()

    return ExtractedDocument(text=full_text, tables=all_tables, metadata=metadata)


def _extract_with_pypdf2(file_path: str) -> ExtractedDocument:
    """Extract using PyPDF2 — fallback, text-only (no table extraction)."""
    from PyPDF2 import PdfReader

    reader = PdfReader(file_path)
    pages_text: list[str] = []

    for page in reader.pages:
        text = page.extract_text()
        if text and text.strip():
            pages_text.append(text)

    full_text = "\n\n".join(pages_text)
    metadata = {
        "title": reader.metadata.title if reader.metadata and reader.metadata.title else os.path.basename(file_path),
        "pages": str(len(reader.pages)),
        "source": os.path.basename(file_path),
        "author": reader.metadata.author if reader.metadata and reader.metadata.author else "",
    }

    return ExtractedDocument(text=full_text, tables=[], metadata=metadata)


async def extract_from_pdf(file_path: str) -> ExtractedDocument:
    """Extract text and tables from a PDF file.

    Tries PyMuPDF first (best quality + table extraction), falls back to
    PyPDF2 (text only). Raises ValueError if the file cannot be read.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    # Try PyMuPDF first
    try:
        result = _extract_with_pymupdf(file_path)
        logger.info(
            "PDF extracted with PyMuPDF: %d chars, %d tables, %s pages",
            len(result.text), len(result.tables), result.metadata.get("pages", "?"),
        )
        return result
    except ImportError:
        logger.info("PyMuPDF not available, falling back to PyPDF2")
    except Exception as exc:
        logger.warning("PyMuPDF extraction failed (%s), falling back to PyPDF2", exc)

    # Fallback to PyPDF2
    try:
        result = _extract_with_pypdf2(file_path)
        logger.info(
            "PDF extracted with PyPDF2: %d chars, %s pages (no table extraction)",
            len(result.text), result.metadata.get("pages", "?"),
        )
        return result
    except ImportError:
        raise RuntimeError(
            "Neither PyMuPDF (pymupdf) nor PyPDF2 is installed. "
            "Install one of them: pip install pymupdf PyPDF2"
        )
    except Exception as exc:
        raise ValueError(f"Failed to extract text from PDF: {exc}") from exc


async def extract_from_text(text: str, title: str = "Untitled") -> ExtractedDocument:
    """Wrap plain text or call notes into an ExtractedDocument."""
    if not text or not text.strip():
        raise ValueError("Input text is empty")

    return ExtractedDocument(
        text=text.strip(),
        tables=[],
        metadata={
            "title": title,
            "pages": "1",
            "source": "plain_text",
        },
    )


# ---------------------------------------------------------------------------
# LLM-based structuring
# ---------------------------------------------------------------------------

STRUCTURE_SYSTEM_PROMPT = """You are an expert at analyzing project documents for the Avni field data collection platform.

Given raw text from a concept note, project proposal, call notes, or requirements document, extract structured information about what needs to be built in Avni.

You MUST respond with ONLY valid JSON (no markdown, no explanation) matching this schema:

{
  "title": "string — project/program title",
  "subject_types": ["Individual", "Household", etc.],
  "programs": ["Maternal Health", "Nutrition", etc.],
  "encounter_types": [
    {"name": "ANC Visit", "program": "Maternal Health", "frequency": "monthly"}
  ],
  "data_fields": [
    {"name": "Weight", "type": "Numeric", "form": "ANC Visit", "section": "Vitals"}
  ],
  "visit_schedules": ["raw text about visit scheduling rules"],
  "rules": ["raw text about conditions, skip logic, decisions"],
  "ambiguities": ["things that are unclear or need clarification"]
}

Guidelines:
- subject_types: Look for mentions of individuals, households, families, groups, communities
- programs: Look for longitudinal tracking programs (pregnancy, nutrition, TB, etc.)
- encounter_types: Map visits/assessments to programs. Include frequency if mentioned.
- data_fields: Extract every data point mentioned. Infer type from context:
  - Numbers/measurements → Numeric (include unit if mentioned)
  - Yes/No, categories → Coded (list options if mentioned)
  - Dates → Date
  - Free text → Text
  - Photos → Image
  - Phone numbers → PhoneNumber
- visit_schedules: Capture any mentions of when visits happen, frequencies, triggers
- rules: Capture conditions, logic, eligibility criteria, referral rules
- ambiguities: Flag anything unclear, contradictory, or missing

Be thorough — extract everything mentioned, even if vague. It's better to over-extract and flag ambiguities than to miss requirements."""


async def structure_content(raw_text: str) -> StructuredRequirements:
    """Use LLM to convert raw extracted text into structured requirement sections.

    Sends the raw text to the LLM with a structuring prompt and parses the
    JSON response into a StructuredRequirements dataclass.
    """
    if not raw_text or not raw_text.strip():
        return StructuredRequirements(ambiguities=["Document is empty — no content to analyze"])

    # Truncate extremely long documents to stay within token limits
    max_chars = 80_000  # ~20K tokens
    truncated = raw_text[:max_chars]
    if len(raw_text) > max_chars:
        truncated += "\n\n[... document truncated for analysis ...]"

    response = await claude_client.complete(
        messages=[{"role": "user", "content": f"Analyze this document and extract structured Avni requirements:\n\n{truncated}"}],
        system_prompt=STRUCTURE_SYSTEM_PROMPT,
    )

    return _parse_structured_response(response)


def _parse_structured_response(response: str) -> StructuredRequirements:
    """Parse the LLM JSON response into a StructuredRequirements dataclass."""
    # Strip markdown code fences if present
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON response for structuring; wrapping as ambiguity")
        return StructuredRequirements(
            ambiguities=[f"Could not parse LLM response as structured JSON. Raw: {response[:500]}"]
        )

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


# ---------------------------------------------------------------------------
# Domain mapping (StructuredRequirements → SRSData)
# ---------------------------------------------------------------------------

DOMAIN_MAP_SYSTEM_PROMPT = """You are the Avni Platform Architect mapping requirements to Avni's data model.

Given structured requirements (subject types, programs, encounters, fields) and reference knowledge from real Avni implementations, produce a complete SRSData JSON that can be used to generate an Avni bundle.

You MUST respond with ONLY valid JSON matching this schema:

{
  "orgName": "string",
  "subjectTypes": [{"name": "Individual", "type": "Person"}],
  "programs": [{"name": "Maternal Health", "colour": "#E91E63", "enrolmentEligibility": true}],
  "encounterTypes": ["ANC Visit", "PNC Visit"],
  "forms": [
    {
      "name": "ANC Visit Form",
      "formType": "ProgramEncounter",
      "programName": "Maternal Health",
      "encounterTypeName": "ANC Visit",
      "groups": [
        {
          "name": "Vitals",
          "fields": [
            {"name": "Weight", "dataType": "Numeric", "mandatory": true, "unit": "kg", "lowAbsolute": 30, "highAbsolute": 200},
            {"name": "Blood Pressure Systolic", "dataType": "Numeric", "mandatory": true, "unit": "mmHg"}
          ]
        }
      ]
    }
  ],
  "groups": ["Everyone"],
  "addressLevelTypes": [{"name": "Village", "level": 1}],
  "programEncounterMappings": [{"encounterType": "ANC Visit", "program": "Maternal Health"}],
  "generalEncounterTypes": ["General Checkup"]
}

Guidelines:
- Map subject_types to Avni SubjectType with correct type (Person, Individual, Household, Group)
- Map programs with appropriate colours (use Indian health program conventions)
- Map encounter_types with correct formType:
  - If encounter belongs to a program → ProgramEncounter
  - If standalone → Encounter
  - Registration forms → IndividualProfile
  - Enrolment forms → ProgramEnrolment
  - Exit forms → ProgramExit
- Map data_fields to proper Avni dataTypes:
  - Numeric (with unit, lowAbsolute, highAbsolute where inferable)
  - Coded (with options array)
  - Text, Date, DateTime, PhoneNumber, Image, Notes
- Group fields by section or form logically
- Use standard Avni conventions for field naming
- Include a Registration form if not explicitly mentioned"""


async def map_to_avni_domain(
    requirements: StructuredRequirements,
    org_name: str = "Organisation",
) -> SRSData:
    """Use LLM + RAG to map unstructured requirements to Avni domain model.

    Enriches the LLM prompt with RAG knowledge about similar implementations
    for better field naming, data types, and structural decisions.
    """
    # Fetch relevant domain knowledge via RAG
    rag_context = ""
    try:
        search_terms = requirements.programs + requirements.subject_types
        if search_terms:
            query = " ".join(search_terms[:5])
            rag_results = await rag_service.search_concepts(query, limit=10)
            if rag_results:
                rag_context = "\n\n--- Reference Knowledge from Avni Implementations ---\n"
                rag_context += "\n".join(f"- {r.text[:300]}" for r in rag_results)
    except Exception as exc:
        logger.warning("RAG search failed during domain mapping: %s", exc)

    # Build the requirements summary
    req_summary = _requirements_to_text(requirements)

    prompt = f"""Map these requirements to Avni's domain model:

{req_summary}

Organization name: {org_name}
{rag_context}"""

    response = await claude_client.complete(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=DOMAIN_MAP_SYSTEM_PROMPT,
    )

    return _parse_srs_response(response, org_name)


def _requirements_to_text(req: StructuredRequirements) -> str:
    """Serialize StructuredRequirements into a readable text summary for LLM."""
    parts: list[str] = []
    if req.title:
        parts.append(f"Title: {req.title}")
    if req.subject_types:
        parts.append(f"Subject Types: {', '.join(req.subject_types)}")
    if req.programs:
        parts.append(f"Programs: {', '.join(req.programs)}")
    if req.encounter_types:
        encounters_text = json.dumps(req.encounter_types, indent=2)
        parts.append(f"Encounter Types:\n{encounters_text}")
    if req.data_fields:
        fields_text = json.dumps(req.data_fields, indent=2)
        parts.append(f"Data Fields:\n{fields_text}")
    if req.visit_schedules:
        parts.append(f"Visit Schedules:\n" + "\n".join(f"- {s}" for s in req.visit_schedules))
    if req.rules:
        parts.append(f"Rules/Logic:\n" + "\n".join(f"- {r}" for r in req.rules))
    if req.ambiguities:
        parts.append(f"Ambiguities:\n" + "\n".join(f"- {a}" for a in req.ambiguities))
    return "\n\n".join(parts)


def _parse_srs_response(response: str, org_name: str) -> SRSData:
    """Parse the LLM JSON response into an SRSData model."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON for domain mapping; returning minimal SRSData")
        return SRSData(orgName=org_name)

    # Parse forms into SRSFormDefinition objects
    forms: list[SRSFormDefinition] = []
    for form_data in data.get("forms", []):
        groups: list[SRSFormGroup] = []
        for group_data in form_data.get("groups", []):
            fields: list[SRSFormField] = []
            for field_data in group_data.get("fields", []):
                fields.append(SRSFormField(
                    name=field_data.get("name", ""),
                    dataType=field_data.get("dataType", "Text"),
                    mandatory=field_data.get("mandatory", True),
                    options=field_data.get("options"),
                    type=field_data.get("type"),
                    unit=field_data.get("unit"),
                    lowAbsolute=field_data.get("lowAbsolute"),
                    highAbsolute=field_data.get("highAbsolute"),
                    keyValues=field_data.get("keyValues"),
                ))
            groups.append(SRSFormGroup(
                name=group_data.get("name", "Default"),
                fields=fields,
            ))
        forms.append(SRSFormDefinition(
            name=form_data.get("name", ""),
            formType=form_data.get("formType", "IndividualProfile"),
            groups=groups,
            programName=form_data.get("programName"),
            encounterTypeName=form_data.get("encounterTypeName"),
        ))

    return SRSData(
        orgName=data.get("orgName", org_name),
        subjectTypes=data.get("subjectTypes", [{"name": "Individual", "type": "Person"}]),
        programs=data.get("programs", []),
        encounterTypes=data.get("encounterTypes", []),
        forms=forms,
        groups=data.get("groups", ["Everyone"]),
        addressLevelTypes=data.get("addressLevelTypes"),
        programEncounterMappings=data.get("programEncounterMappings"),
        generalEncounterTypes=data.get("generalEncounterTypes"),
    )


# ---------------------------------------------------------------------------
# Clarification generation
# ---------------------------------------------------------------------------

CLARIFY_SYSTEM_PROMPT = """You are an expert Avni implementation consultant reviewing requirements for completeness.

Given structured requirements and a domain mapping, identify gaps, ambiguities, and missing information that would block a production-quality Avni implementation.

You MUST respond with ONLY valid JSON — an array of clarification questions:

[
  {
    "question": "What should happen when a pregnant woman misses her scheduled ANC visit?",
    "context": "The visit schedule mentions monthly ANC visits but doesn't specify overdue handling",
    "options": ["Auto-reschedule after 7 days", "Alert supervisor", "Both"],
    "field": "ANC Visit schedule"
  }
]

Focus on:
1. Missing data types for fields (e.g. "Status" without coded options)
2. Unclear visit frequencies or scheduling triggers
3. Missing eligibility or exit criteria for programs
4. Unspecified skip logic or decision rules
5. Missing form groupings or sections
6. Ambiguous field names that could mean different things
7. Missing subject type details (is it Person, Individual, Household?)
8. Missing address hierarchy levels
9. Unclear user roles and permissions
10. Missing cancellation or exit forms

Generate 3-10 questions, prioritized by impact on implementation."""


async def generate_clarifications(
    requirements: StructuredRequirements,
    mapped: SRSData,
) -> list[ClarificationQuestion]:
    """Identify ambiguous parts and generate targeted questions.

    Compares the raw requirements against the domain mapping to find gaps,
    inconsistencies, and missing information.
    """
    req_text = _requirements_to_text(requirements)
    mapped_summary = json.dumps(mapped.model_dump(), indent=2, default=str)

    # Truncate if too long
    if len(mapped_summary) > 30_000:
        mapped_summary = mapped_summary[:30_000] + "\n... [truncated]"

    prompt = f"""Review these requirements and domain mapping for completeness:

## Extracted Requirements
{req_text}

## Domain Mapping (SRSData)
{mapped_summary}

Generate clarification questions for anything unclear or missing."""

    response = await claude_client.complete(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=CLARIFY_SYSTEM_PROMPT,
    )

    return _parse_clarifications(response)


def _parse_clarifications(response: str) -> list[ClarificationQuestion]:
    """Parse the LLM JSON response into ClarificationQuestion objects."""
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("LLM returned non-JSON for clarifications")
        return [
            ClarificationQuestion(
                question="Could not generate structured clarification questions. Please review the requirements manually.",
                context="LLM response parsing failed",
            )
        ]

    questions: list[ClarificationQuestion] = []
    items = data if isinstance(data, list) else data.get("questions", data.get("clarifications", []))

    for item in items:
        if isinstance(item, dict):
            questions.append(ClarificationQuestion(
                question=item.get("question", ""),
                context=item.get("context", ""),
                options=item.get("options"),
                field=item.get("field"),
            ))
        elif isinstance(item, str):
            questions.append(ClarificationQuestion(question=item, context=""))

    return questions


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

@dataclass
class DocumentProcessingResult:
    """Complete result of the document processing pipeline."""

    extracted: ExtractedDocument
    requirements: StructuredRequirements
    srs_data: SRSData
    clarifications: list[ClarificationQuestion]


async def process_document(
    file_path: str | None = None,
    raw_text: str | None = None,
    title: str = "Untitled",
    org_name: str = "Organisation",
) -> DocumentProcessingResult:
    """Run the full extraction pipeline: extract → structure → map → clarify.

    Provide either file_path (for PDF) or raw_text (for plain text / call notes).
    Returns the complete result including SRSData and clarification questions.
    """
    # Step 1: Extract
    if file_path:
        extracted = await extract_from_pdf(file_path)
    elif raw_text:
        extracted = await extract_from_text(raw_text, title=title)
    else:
        raise ValueError("Either file_path or raw_text must be provided")

    if not extracted.text.strip():
        raise ValueError("No text could be extracted from the document")

    # Include table content in the text for structuring
    full_text = extracted.text
    if extracted.tables:
        table_texts = []
        for i, table in enumerate(extracted.tables, 1):
            rows = [" | ".join(row) for row in table]
            table_texts.append(f"\n[Table {i}]\n" + "\n".join(rows))
        full_text += "\n\n--- Extracted Tables ---" + "".join(table_texts)

    # Step 2: Structure
    requirements = await structure_content(full_text)
    if not requirements.title and extracted.metadata.get("title"):
        requirements.title = extracted.metadata["title"]

    # Step 3: Map to domain
    srs_data = await map_to_avni_domain(requirements, org_name=org_name)

    # Step 4: Generate clarifications
    clarifications = await generate_clarifications(requirements, srs_data)

    return DocumentProcessingResult(
        extracted=extracted,
        requirements=requirements,
        srs_data=srs_data,
        clarifications=clarifications,
    )
