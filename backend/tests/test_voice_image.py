"""Tests for voice mapper and image extractor services.

Covers:
- Voice transcript to form field mapping
- Image data extraction
- Field context building
- Language handling
- Edge cases: empty inputs, malformed forms
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.voice_mapper import map_transcript, _build_field_context as voice_build_context
from app.services.image_extractor import extract_from_image, _build_field_context as image_build_context


# ── Sample Form Data ─────────────────────────────────────────────────────────

SAMPLE_FORM = {
    "name": "ANC Visit",
    "formElementGroups": [
        {
            "name": "Vitals",
            "formElements": [
                {
                    "name": "Weight",
                    "concept": {
                        "name": "Weight",
                        "dataType": "Numeric",
                        "unit": "kg",
                        "lowAbsolute": 30,
                        "highAbsolute": 200,
                    },
                },
                {
                    "name": "BP Systolic",
                    "concept": {
                        "name": "BP Systolic",
                        "dataType": "Numeric",
                        "unit": "mmHg",
                    },
                },
                {
                    "name": "Complaints",
                    "concept": {
                        "name": "Complaints",
                        "dataType": "Coded",
                        "answers": [
                            {"name": "Headache"},
                            {"name": "Nausea"},
                            {"name": "None"},
                        ],
                    },
                },
            ],
        }
    ],
}

EMPTY_FORM = {"name": "Empty", "formElementGroups": []}
MINIMAL_FORM = {
    "name": "Basic",
    "formElementGroups": [
        {
            "name": "Group",
            "formElements": [
                {"concept": {"name": "Field1", "dataType": "Text"}},
            ],
        }
    ],
}


# ── Voice Mapper Field Context ───────────────────────────────────────────────


class TestVoiceFieldContext:
    def test_builds_context_with_fields(self):
        context = voice_build_context(SAMPLE_FORM)
        assert "Weight" in context
        assert "BP Systolic" in context
        assert "Complaints" in context

    def test_includes_data_type(self):
        context = voice_build_context(SAMPLE_FORM)
        assert "Numeric" in context

    def test_includes_unit(self):
        context = voice_build_context(SAMPLE_FORM)
        assert "kg" in context

    def test_includes_coded_options(self):
        context = voice_build_context(SAMPLE_FORM)
        assert "Headache" in context
        assert "Nausea" in context

    def test_includes_range(self):
        context = voice_build_context(SAMPLE_FORM)
        assert "30" in context
        assert "200" in context

    def test_empty_form(self):
        context = voice_build_context(EMPTY_FORM)
        assert context == "" or "Field" not in context

    def test_form_without_concept_name(self):
        form = {
            "formElementGroups": [{
                "formElements": [{"concept": {"dataType": "Text"}}],
            }],
        }
        context = voice_build_context(form)
        # Should handle missing name gracefully
        assert isinstance(context, str)


# ── Voice Mapper ─────────────────────────────────────────────────────────────


class TestVoiceMapper:
    @pytest.mark.asyncio
    async def test_map_transcript_success(self):
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"fields": {"Weight": "55"}, "confidence": {"Weight": 0.9}, "unmapped_text": ""}')
            result = await map_transcript("patient weight is 55 kg", SAMPLE_FORM, "en")
            assert "fields" in result
            assert "Weight" in result["fields"]

    @pytest.mark.asyncio
    async def test_map_transcript_hindi(self):
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"fields": {"Weight": "60"}, "confidence": {"Weight": 0.85}, "unmapped_text": ""}')
            result = await map_transcript("वजन 60 किलो है", SAMPLE_FORM, "hi")
            assert "fields" in result

    @pytest.mark.asyncio
    async def test_map_transcript_with_unmapped(self):
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"fields": {}, "confidence": {}, "unmapped_text": "something unrelated"}')
            result = await map_transcript("something unrelated", SAMPLE_FORM)
            assert result["unmapped_text"] == "something unrelated"

    @pytest.mark.asyncio
    async def test_map_transcript_llm_failure(self):
        """LLM failure should be caught and return empty fallback."""
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(side_effect=Exception("LLM Error"))
            result = await map_transcript("weight is 55", SAMPLE_FORM)
            assert result["fields"] == {}
            assert result["unmapped_text"] == "weight is 55"

    @pytest.mark.asyncio
    async def test_map_transcript_invalid_json_response(self):
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value="not valid json")
            result = await map_transcript("weight is 55", SAMPLE_FORM)
            assert result["fields"] == {}

    @pytest.mark.asyncio
    async def test_map_transcript_markdown_wrapped_json(self):
        with patch("app.services.voice_mapper.claude_client") as mock_client:
            mock_client.complete = AsyncMock(
                return_value='```json\n{"fields": {"Weight": "55"}, "confidence": {"Weight": 0.9}, "unmapped_text": ""}\n```'
            )
            result = await map_transcript("weight is 55", SAMPLE_FORM)
            assert "fields" in result


# ── Image Extractor Field Context ────────────────────────────────────────────


class TestImageFieldContext:
    def test_builds_context_with_fields(self):
        context = image_build_context(SAMPLE_FORM)
        assert "Weight" in context
        assert "Complaints" in context

    def test_empty_form(self):
        context = image_build_context(EMPTY_FORM)
        assert isinstance(context, str)


# ── Image Extractor ──────────────────────────────────────────────────────────


class TestImageExtractor:
    @pytest.mark.asyncio
    async def test_extract_from_image_success(self):
        with patch("app.services.image_extractor.claude_client") as mock_client:
            mock_client.complete_with_vision = AsyncMock(
                return_value='{"fields": {"Weight": "55", "BP Systolic": "120"}, "confidence": {"Weight": 0.9, "BP Systolic": 0.85}, "notes": "Clear handwriting"}'
            )
            result = await extract_from_image(b"fake_image_bytes", SAMPLE_FORM)
            assert "fields" in result
            assert "Weight" in result["fields"]

    @pytest.mark.asyncio
    async def test_extract_from_image_llm_failure(self):
        """LLM failure should be caught and return empty fallback."""
        with patch("app.services.image_extractor.claude_client") as mock_client:
            mock_client.complete_with_vision = AsyncMock(side_effect=Exception("Vision API Error"))
            result = await extract_from_image(b"fake_image", SAMPLE_FORM)
            assert result["fields"] == {}

    @pytest.mark.asyncio
    async def test_extract_from_image_invalid_json(self):
        with patch("app.services.image_extractor.claude_client") as mock_client:
            mock_client.complete_with_vision = AsyncMock(return_value="not json")
            result = await extract_from_image(b"fake_image", SAMPLE_FORM)
            assert result["fields"] == {}

    @pytest.mark.asyncio
    async def test_extract_from_image_with_notes(self):
        with patch("app.services.image_extractor.claude_client") as mock_client:
            mock_client.complete_with_vision = AsyncMock(
                return_value='{"fields": {"Weight": "55"}, "confidence": {"Weight": 0.7}, "notes": "Blurry image, low confidence"}'
            )
            result = await extract_from_image(b"fake_image", SAMPLE_FORM)
            assert "notes" in result
