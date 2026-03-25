"""Tests for the document extractor service and router.

Covers:
- PDF extraction (with mocked libraries)
- Text extraction
- LLM-based content structuring
- Domain mapping to SRSData
- Clarification question generation
- Full pipeline end-to-end
- Error handling and edge cases
"""

import json
import os
import tempfile
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.schemas import SRSData
from app.services.document_extractor import (
    ClarificationQuestion,
    DocumentProcessingResult,
    ExtractedDocument,
    StructuredRequirements,
    _parse_clarifications,
    _parse_srs_response,
    _parse_structured_response,
    _requirements_to_text,
    extract_from_pdf,
    extract_from_text,
    generate_clarifications,
    map_to_avni_domain,
    process_document,
    structure_content,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_raw_text():
    """A realistic concept note for an MCH program."""
    return """
    Maternal and Child Health Program — Concept Note

    Organization: Rural Health Foundation
    Location: Jharkhand, India

    The program aims to track pregnant women through antenatal care visits.
    Field workers (ASHAs) will register pregnant women in their villages.

    Subject Types: Individual (pregnant women), Household

    Programs:
    - Maternal Health: Track from registration through delivery and postnatal period
    - Child Health: Track newborns for immunization and growth monitoring

    Visits:
    - ANC Visit: Monthly during pregnancy. Capture weight, blood pressure, hemoglobin, urine test.
    - PNC Visit: At 3, 7, and 42 days after delivery.
    - Growth Monitoring: Monthly for children under 5. Measure weight, height, MUAC.

    Data to collect:
    - Weight (kg), Height (cm), BP systolic, BP diastolic, Hemoglobin (g/dL)
    - LMP date, EDD, Gravida, Parity
    - High-risk pregnancy: Yes/No
    - Delivery type: Normal/Cesarean/Assisted
    - Birth weight of newborn
    - Immunization status

    Rules:
    - If hemoglobin < 7, refer to PHC immediately
    - If BP systolic > 140 or BP diastolic > 90, flag as high risk
    - Schedule next ANC visit 28 days from current visit

    The program will be used by 50 ASHAs and 10 supervisors across 3 blocks.
    """


@pytest.fixture
def sample_structured_requirements():
    return StructuredRequirements(
        title="Maternal and Child Health Program",
        subject_types=["Individual", "Household"],
        programs=["Maternal Health", "Child Health"],
        encounter_types=[
            {"name": "ANC Visit", "program": "Maternal Health", "frequency": "monthly"},
            {"name": "PNC Visit", "program": "Maternal Health", "frequency": "3, 7, 42 days postpartum"},
            {"name": "Growth Monitoring", "program": "Child Health", "frequency": "monthly"},
        ],
        data_fields=[
            {"name": "Weight", "type": "Numeric", "form": "ANC Visit", "section": "Vitals"},
            {"name": "Height", "type": "Numeric", "form": "Growth Monitoring", "section": "Anthropometry"},
            {"name": "Blood Pressure Systolic", "type": "Numeric", "form": "ANC Visit", "section": "Vitals"},
            {"name": "Hemoglobin", "type": "Numeric", "form": "ANC Visit", "section": "Lab"},
            {"name": "High Risk Pregnancy", "type": "Coded", "form": "ANC Visit", "section": "Assessment"},
            {"name": "Delivery Type", "type": "Coded", "form": "Delivery", "section": "Delivery Details"},
        ],
        visit_schedules=["ANC visits monthly", "PNC at 3, 7, 42 days", "Growth monitoring monthly"],
        rules=["If hemoglobin < 7, refer to PHC", "If BP > 140/90, flag as high risk"],
        ambiguities=["Immunization details not specified"],
    )


@pytest.fixture
def sample_srs_data():
    return SRSData(
        orgName="Rural Health Foundation",
        subjectTypes=[{"name": "Individual", "type": "Person"}],
        programs=[{"name": "Maternal Health", "colour": "#E91E63"}],
        encounterTypes=["ANC Visit", "PNC Visit"],
        forms=[],
        groups=["Everyone"],
    )


@pytest.fixture
def mock_llm_structure_response():
    """Mock LLM response for structure_content."""
    return json.dumps({
        "title": "MCH Program",
        "subject_types": ["Individual", "Household"],
        "programs": ["Maternal Health", "Child Health"],
        "encounter_types": [
            {"name": "ANC Visit", "program": "Maternal Health", "frequency": "monthly"}
        ],
        "data_fields": [
            {"name": "Weight", "type": "Numeric", "form": "ANC Visit", "section": "Vitals"}
        ],
        "visit_schedules": ["Monthly ANC visits"],
        "rules": ["If hemoglobin < 7, refer"],
        "ambiguities": ["Immunization details missing"],
    })


@pytest.fixture
def mock_llm_map_response():
    """Mock LLM response for map_to_avni_domain."""
    return json.dumps({
        "orgName": "Rural Health Foundation",
        "subjectTypes": [{"name": "Individual", "type": "Person"}],
        "programs": [{"name": "Maternal Health", "colour": "#E91E63", "enrolmentEligibility": True}],
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
                            {"name": "Weight", "dataType": "Numeric", "mandatory": True, "unit": "kg"},
                            {"name": "Blood Pressure Systolic", "dataType": "Numeric", "mandatory": True, "unit": "mmHg"},
                        ],
                    }
                ],
            }
        ],
        "groups": ["Everyone"],
    })


@pytest.fixture
def mock_llm_clarify_response():
    """Mock LLM response for generate_clarifications."""
    return json.dumps([
        {
            "question": "What immunizations should be tracked for children?",
            "context": "Immunization status mentioned but specific vaccines not listed",
            "options": ["BCG, OPV, DPT, Measles", "Full national immunization schedule"],
            "field": "Immunization status",
        },
        {
            "question": "Should high-risk pregnancies have more frequent visits?",
            "context": "High-risk flag mentioned but no differential scheduling",
            "options": ["Weekly visits", "Bi-weekly visits", "Same as normal"],
            "field": "ANC Visit schedule",
        },
        {
            "question": "What are the coded options for delivery type?",
            "context": "Delivery type field needs specific options",
            "options": None,
            "field": "Delivery Type",
        },
    ])


# ---------------------------------------------------------------------------
# Test: Text extraction
# ---------------------------------------------------------------------------

class TestExtractFromText:
    @pytest.mark.asyncio
    async def test_extract_plain_text(self, sample_raw_text):
        result = await extract_from_text(sample_raw_text, title="MCH Concept Note")
        assert isinstance(result, ExtractedDocument)
        assert "Maternal and Child Health" in result.text
        assert result.metadata["title"] == "MCH Concept Note"
        assert result.metadata["source"] == "plain_text"
        assert result.tables == []

    @pytest.mark.asyncio
    async def test_extract_empty_text_raises(self):
        with pytest.raises(ValueError, match="empty"):
            await extract_from_text("")

    @pytest.mark.asyncio
    async def test_extract_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="empty"):
            await extract_from_text("   \n\t  ")

    @pytest.mark.asyncio
    async def test_extract_text_default_title(self):
        result = await extract_from_text("Some content")
        assert result.metadata["title"] == "Untitled"


# ---------------------------------------------------------------------------
# Test: PDF extraction
# ---------------------------------------------------------------------------

class TestExtractFromPdf:
    @pytest.mark.asyncio
    async def test_pdf_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            await extract_from_pdf("/nonexistent/path.pdf")

    @pytest.mark.asyncio
    async def test_pdf_extract_with_pymupdf(self):
        """Test PyMuPDF extraction path with mocked fitz."""
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Page 1 content about maternal health"
        mock_page.find_tables.side_effect = AttributeError("no find_tables")

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_doc.__enter__ = lambda self: self
        mock_doc.__exit__ = lambda self, *a: None
        mock_doc.page_count = 1
        mock_doc.metadata = {"title": "Test PDF", "author": "Test Author"}

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 fake")
            tmp_path = tmp.name

        try:
            with patch("app.services.document_extractor._extract_with_pymupdf") as mock_extract:
                mock_extract.return_value = ExtractedDocument(
                    text="Page 1 content about maternal health",
                    tables=[],
                    metadata={"title": "Test PDF", "pages": "1", "source": os.path.basename(tmp_path), "author": "Test Author"},
                )
                result = await extract_from_pdf(tmp_path)
                assert "maternal health" in result.text
                assert result.metadata["title"] == "Test PDF"
        finally:
            os.unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_pdf_extract_fallback_to_pypdf2(self):
        """Test fallback to PyPDF2 when PyMuPDF fails."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"%PDF-1.4 fake")
            tmp_path = tmp.name

        try:
            with patch("app.services.document_extractor._extract_with_pymupdf", side_effect=ImportError("no fitz")), \
                 patch("app.services.document_extractor._extract_with_pypdf2") as mock_pypdf2:
                mock_pypdf2.return_value = ExtractedDocument(
                    text="Fallback extracted text",
                    tables=[],
                    metadata={"title": "Fallback", "pages": "1", "source": os.path.basename(tmp_path), "author": ""},
                )
                result = await extract_from_pdf(tmp_path)
                assert result.text == "Fallback extracted text"
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Test: Content structuring
# ---------------------------------------------------------------------------

class TestStructureContent:
    @pytest.mark.asyncio
    async def test_structure_content(self, sample_raw_text, mock_llm_structure_response):
        with patch.object(
            __import__("app.services.document_extractor", fromlist=["claude_client"]).claude_client,
            "complete",
            new_callable=AsyncMock,
            return_value=mock_llm_structure_response,
        ):
            result = await structure_content(sample_raw_text)
            assert isinstance(result, StructuredRequirements)
            assert result.title == "MCH Program"
            assert "Individual" in result.subject_types
            assert "Maternal Health" in result.programs
            assert len(result.encounter_types) > 0
            assert len(result.data_fields) > 0

    @pytest.mark.asyncio
    async def test_structure_empty_text(self):
        result = await structure_content("")
        assert len(result.ambiguities) > 0
        assert "empty" in result.ambiguities[0].lower()

    def test_parse_structured_response_valid(self, mock_llm_structure_response):
        result = _parse_structured_response(mock_llm_structure_response)
        assert result.title == "MCH Program"
        assert len(result.programs) == 2

    def test_parse_structured_response_with_code_fence(self, mock_llm_structure_response):
        fenced = f"```json\n{mock_llm_structure_response}\n```"
        result = _parse_structured_response(fenced)
        assert result.title == "MCH Program"

    def test_parse_structured_response_invalid_json(self):
        result = _parse_structured_response("This is not JSON at all")
        assert len(result.ambiguities) > 0
        assert "Could not parse" in result.ambiguities[0]

    def test_parse_structured_response_empty_fields(self):
        result = _parse_structured_response(json.dumps({"title": "Test"}))
        assert result.title == "Test"
        assert result.subject_types == []
        assert result.programs == []


# ---------------------------------------------------------------------------
# Test: Domain mapping
# ---------------------------------------------------------------------------

class TestMapToAvniDomain:
    @pytest.mark.asyncio
    async def test_map_to_domain(self, sample_structured_requirements, mock_llm_map_response):
        with patch.object(
            __import__("app.services.document_extractor", fromlist=["claude_client"]).claude_client,
            "complete",
            new_callable=AsyncMock,
            return_value=mock_llm_map_response,
        ), patch.object(
            __import__("app.services.document_extractor", fromlist=["rag_service"]).rag_service,
            "search_concepts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await map_to_avni_domain(
                sample_structured_requirements,
                org_name="Rural Health Foundation",
            )
            assert isinstance(result, SRSData)
            assert result.orgName == "Rural Health Foundation"
            assert len(result.programs) > 0
            assert len(result.forms) > 0
            assert result.forms[0].name == "ANC Visit Form"
            assert result.forms[0].formType == "ProgramEncounter"

    def test_parse_srs_response_valid(self, mock_llm_map_response):
        result = _parse_srs_response(mock_llm_map_response, "TestOrg")
        assert isinstance(result, SRSData)
        assert result.orgName == "Rural Health Foundation"
        assert len(result.forms) == 1
        assert result.forms[0].groups[0].name == "Vitals"
        assert len(result.forms[0].groups[0].fields) == 2

    def test_parse_srs_response_invalid_json(self):
        result = _parse_srs_response("not json", "FallbackOrg")
        assert isinstance(result, SRSData)
        assert result.orgName == "FallbackOrg"

    def test_parse_srs_response_with_code_fence(self, mock_llm_map_response):
        fenced = f"```json\n{mock_llm_map_response}\n```"
        result = _parse_srs_response(fenced, "TestOrg")
        assert result.orgName == "Rural Health Foundation"


# ---------------------------------------------------------------------------
# Test: Clarification generation
# ---------------------------------------------------------------------------

class TestClarifications:
    @pytest.mark.asyncio
    async def test_generate_clarifications(
        self, sample_structured_requirements, sample_srs_data, mock_llm_clarify_response,
    ):
        with patch.object(
            __import__("app.services.document_extractor", fromlist=["claude_client"]).claude_client,
            "complete",
            new_callable=AsyncMock,
            return_value=mock_llm_clarify_response,
        ):
            result = await generate_clarifications(sample_structured_requirements, sample_srs_data)
            assert isinstance(result, list)
            assert len(result) == 3
            assert all(isinstance(q, ClarificationQuestion) for q in result)
            assert "immunization" in result[0].question.lower()

    def test_parse_clarifications_valid(self, mock_llm_clarify_response):
        result = _parse_clarifications(mock_llm_clarify_response)
        assert len(result) == 3
        assert result[0].options is not None
        assert result[2].options is None
        assert result[0].field == "Immunization status"

    def test_parse_clarifications_invalid_json(self):
        result = _parse_clarifications("not json")
        assert len(result) == 1
        assert "Could not generate" in result[0].question

    def test_parse_clarifications_with_code_fence(self, mock_llm_clarify_response):
        fenced = f"```json\n{mock_llm_clarify_response}\n```"
        result = _parse_clarifications(fenced)
        assert len(result) == 3

    def test_parse_clarifications_string_items(self):
        """Handle case where LLM returns simple string questions."""
        data = json.dumps(["What about immunizations?", "What about exit criteria?"])
        result = _parse_clarifications(data)
        assert len(result) == 2
        assert result[0].question == "What about immunizations?"
        assert result[0].context == ""


# ---------------------------------------------------------------------------
# Test: Requirements to text serialization
# ---------------------------------------------------------------------------

class TestRequirementsToText:
    def test_full_requirements(self, sample_structured_requirements):
        text = _requirements_to_text(sample_structured_requirements)
        assert "Maternal and Child Health" in text
        assert "Individual" in text
        assert "Maternal Health" in text
        assert "ANC Visit" in text
        assert "Weight" in text
        assert "hemoglobin" in text.lower()

    def test_empty_requirements(self):
        text = _requirements_to_text(StructuredRequirements())
        assert text == ""  # all fields empty, no parts

    def test_partial_requirements(self):
        req = StructuredRequirements(title="Test", programs=["MCH"])
        text = _requirements_to_text(req)
        assert "Test" in text
        assert "MCH" in text


# ---------------------------------------------------------------------------
# Test: Full pipeline
# ---------------------------------------------------------------------------

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_with_text(
        self, sample_raw_text, mock_llm_structure_response, mock_llm_map_response, mock_llm_clarify_response,
    ):
        call_count = 0

        async def mock_complete(messages, system_prompt=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_llm_structure_response
            elif call_count == 2:
                return mock_llm_map_response
            else:
                return mock_llm_clarify_response

        with patch.object(
            __import__("app.services.document_extractor", fromlist=["claude_client"]).claude_client,
            "complete",
            side_effect=mock_complete,
        ), patch.object(
            __import__("app.services.document_extractor", fromlist=["rag_service"]).rag_service,
            "search_concepts",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await process_document(
                raw_text=sample_raw_text,
                title="MCH Concept Note",
                org_name="Rural Health Foundation",
            )

            assert isinstance(result, DocumentProcessingResult)
            assert isinstance(result.extracted, ExtractedDocument)
            assert isinstance(result.requirements, StructuredRequirements)
            assert isinstance(result.srs_data, SRSData)
            assert isinstance(result.clarifications, list)
            assert result.requirements.title == "MCH Program"
            assert result.srs_data.orgName == "Rural Health Foundation"
            assert len(result.clarifications) == 3

    @pytest.mark.asyncio
    async def test_pipeline_no_input_raises(self):
        with pytest.raises(ValueError, match="Either file_path or raw_text"):
            await process_document()

    @pytest.mark.asyncio
    async def test_pipeline_empty_extraction_raises(self):
        with pytest.raises(ValueError, match="empty"):
            await process_document(raw_text="   ")


# ---------------------------------------------------------------------------
# Test: Data model construction
# ---------------------------------------------------------------------------

class TestDataModels:
    def test_extracted_document_defaults(self):
        doc = ExtractedDocument(text="hello")
        assert doc.tables == []
        assert doc.metadata == {}

    def test_structured_requirements_defaults(self):
        req = StructuredRequirements()
        assert req.title == ""
        assert req.subject_types == []
        assert req.programs == []
        assert req.encounter_types == []
        assert req.data_fields == []
        assert req.visit_schedules == []
        assert req.rules == []
        assert req.ambiguities == []

    def test_clarification_question_defaults(self):
        q = ClarificationQuestion(question="Test?", context="ctx")
        assert q.options is None
        assert q.field is None

    def test_clarification_question_full(self):
        q = ClarificationQuestion(
            question="What about X?",
            context="X is ambiguous",
            options=["A", "B"],
            field="X field",
        )
        assert q.options == ["A", "B"]
        assert q.field == "X field"
