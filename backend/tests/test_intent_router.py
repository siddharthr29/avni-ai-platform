"""Tests for intent classification: keyword matching, parameter extraction, Claude fallback.

Covers:
- Keyword classification for all intent types (BUNDLE, RULE, VOICE, IMAGE, CONFIG, SUPPORT, KNOWLEDGE)
- Confidence scoring
- Parameter extraction (language, org_name)
- Attachment-based classification
- Claude fallback behavior
- Edge cases: empty messages, ambiguous queries
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from app.services.intent_router import (
    classify_intent,
    _keyword_classify,
    _extract_params,
    INTENT_KEYWORDS,
)
from app.models.schemas import IntentType, IntentResult


# ── Keyword Classification ───────────────────────────────────────────────────


class TestKeywordClassification:
    def test_bundle_intent(self):
        result = _keyword_classify("I want to generate a bundle from my SRS")
        assert result is not None
        assert result.intent == IntentType.BUNDLE

    def test_bundle_intent_excel(self):
        result = _keyword_classify("upload srs and create implementation bundle")
        assert result is not None
        assert result.intent == IntentType.BUNDLE

    def test_rule_intent(self):
        result = _keyword_classify("write a skip logic rule for age validation")
        assert result is not None
        assert result.intent == IntentType.RULE

    def test_rule_intent_js(self):
        result = _keyword_classify("create a javascript rule for visit scheduling")
        assert result is not None
        assert result.intent == IntentType.RULE

    def test_voice_intent(self):
        result = _keyword_classify("I want to capture voice data in Hindi")
        assert result is not None
        assert result.intent == IntentType.VOICE

    def test_image_intent(self):
        result = _keyword_classify("extract data from this image of a register")
        assert result is not None
        assert result.intent == IntentType.IMAGE

    def test_config_intent(self):
        result = _keyword_classify("create subject type and configure avni setup")
        assert result is not None
        assert result.intent == IntentType.CONFIG

    def test_support_intent(self):
        result = _keyword_classify("sync is not working, getting error")
        assert result is not None
        assert result.intent == IntentType.SUPPORT

    def test_knowledge_intent(self):
        result = _keyword_classify("what is a form mapping in Avni?")
        assert result is not None
        assert result.intent == IntentType.KNOWLEDGE

    def test_no_match_returns_none(self):
        result = _keyword_classify("hello there")
        assert result is None

    def test_generic_greeting_no_match(self):
        result = _keyword_classify("good morning, how are you?")
        assert result is None


# ── Confidence Scoring ───────────────────────────────────────────────────────


class TestConfidenceScoring:
    def test_single_keyword_base_confidence(self):
        result = _keyword_classify("bundle")
        assert result is not None
        assert 0.25 <= result.confidence <= 0.5

    def test_multiple_keywords_higher_confidence(self):
        result = _keyword_classify("generate bundle from SRS with concepts.json")
        assert result is not None
        assert result.confidence > 0.4

    def test_confidence_capped_below_1(self):
        # Even with many matches, shouldn't exceed 0.95
        result = _keyword_classify(
            "generate bundle from srs upload srs concepts.json forms.json "
            "formmappings groupprivilege zip file bundle zip implementation bundle create bundle"
        )
        assert result is not None
        assert result.confidence <= 0.95

    def test_best_intent_wins(self):
        """When multiple intents match, highest score should win."""
        result = _keyword_classify("create a rule for bundle validation")
        assert result is not None
        # Both RULE and BUNDLE keywords match, best score should win
        assert result.intent in (IntentType.RULE, IntentType.BUNDLE)


# ── Parameter Extraction ─────────────────────────────────────────────────────


class TestParameterExtraction:
    def test_voice_language_hindi(self):
        params = _extract_params("capture voice data in hindi", IntentType.VOICE)
        assert params.get("language") == "hi"

    def test_voice_language_tamil(self):
        params = _extract_params("voice input in tamil", IntentType.VOICE)
        assert params.get("language") == "ta"

    def test_voice_language_telugu(self):
        params = _extract_params("speech in telugu", IntentType.VOICE)
        assert params.get("language") == "te"

    def test_voice_language_english(self):
        params = _extract_params("voice capture in english", IntentType.VOICE)
        assert params.get("language") == "en"

    def test_voice_no_language(self):
        params = _extract_params("capture voice data", IntentType.VOICE)
        assert "language" not in params

    def test_bundle_org_name_extraction(self):
        params = _extract_params("generate bundle for myorg health", IntentType.BUNDLE)
        assert "org_name" in params

    def test_bundle_no_org_name(self):
        params = _extract_params("generate a bundle", IntentType.BUNDLE)
        assert "org_name" not in params

    def test_non_voice_no_language(self):
        params = _extract_params("create a form in hindi", IntentType.BUNDLE)
        assert "language" not in params


# ── Attachment-Based Classification ──────────────────────────────────────────


class TestAttachmentClassification:
    @pytest.mark.asyncio
    async def test_image_attachment(self):
        att = MagicMock(type="image", filename="photo.jpg")
        result = await classify_intent("process this", attachments=[att])
        assert result.intent == IntentType.IMAGE
        assert result.confidence == 0.90

    @pytest.mark.asyncio
    async def test_xlsx_attachment(self):
        att = MagicMock(type="file", filename="srs.xlsx")
        result = await classify_intent("upload this file", attachments=[att])
        assert result.intent == IntentType.BUNDLE
        assert result.confidence == 0.90

    @pytest.mark.asyncio
    async def test_csv_attachment(self):
        att = MagicMock(type="file", filename="data.csv")
        result = await classify_intent("process this csv", attachments=[att])
        assert result.intent == IntentType.BUNDLE

    @pytest.mark.asyncio
    async def test_json_attachment(self):
        att = MagicMock(type="file", filename="concepts.json")
        result = await classify_intent("review this", attachments=[att])
        assert result.intent == IntentType.BUNDLE
        assert result.confidence == 0.80

    @pytest.mark.asyncio
    async def test_attachment_takes_priority(self):
        """Attachment classification should take priority over keywords."""
        att = MagicMock(type="image", filename="register.jpg")
        result = await classify_intent("write a rule for this image", attachments=[att])
        assert result.intent == IntentType.IMAGE

    @pytest.mark.asyncio
    async def test_no_attachments(self):
        """Should fall through to keyword classification."""
        result = await classify_intent("generate a bundle from SRS")
        assert result.intent == IntentType.BUNDLE


# ── Claude Fallback ──────────────────────────────────────────────────────────


class TestClaudeFallback:
    @pytest.mark.asyncio
    async def test_ambiguous_message_falls_to_claude(self):
        """Ambiguous message should fall to Claude."""
        with patch("app.services.intent_router.claude_client") as mock_client:
            mock_client.complete = AsyncMock(
                return_value='{"intent": "chat", "confidence": 0.8, "extracted_params": {}}'
            )
            result = await classify_intent("hello there, nice day")
            assert result.intent == IntentType.CHAT

    @pytest.mark.asyncio
    async def test_claude_failure_defaults_to_chat(self):
        """If Claude fails, should default to CHAT."""
        with patch("app.services.intent_router.claude_client") as mock_client:
            mock_client.complete = AsyncMock(side_effect=Exception("API error"))
            result = await classify_intent("some ambiguous message")
            assert result.intent == IntentType.CHAT
            assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_claude_returns_markdown_json(self):
        """Claude response wrapped in markdown code blocks."""
        with patch("app.services.intent_router.claude_client") as mock_client:
            mock_client.complete = AsyncMock(
                return_value='```json\n{"intent": "support", "confidence": 0.9}\n```'
            )
            result = await classify_intent("ambiguous problem text")
            assert result.intent == IntentType.SUPPORT

    @pytest.mark.asyncio
    async def test_claude_returns_invalid_json(self):
        """Invalid JSON should fall back to CHAT."""
        with patch("app.services.intent_router.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value="not valid json at all")
            result = await classify_intent("ambiguous message")
            assert result.intent == IntentType.CHAT

    @pytest.mark.asyncio
    async def test_claude_returns_invalid_intent(self):
        """Unknown intent type should fall back to CHAT."""
        with patch("app.services.intent_router.claude_client") as mock_client:
            mock_client.complete = AsyncMock(
                return_value='{"intent": "unknown_intent", "confidence": 0.9}'
            )
            result = await classify_intent("ambiguous message")
            assert result.intent == IntentType.CHAT


# ── Edge Cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_message(self):
        result = _keyword_classify("")
        assert result is None

    def test_whitespace_only(self):
        result = _keyword_classify("   ")
        assert result is None

    def test_case_insensitive(self):
        result = _keyword_classify("GENERATE BUNDLE FROM SRS")
        assert result is not None
        assert result.intent == IntentType.BUNDLE

    def test_all_intent_types_have_keywords(self):
        """Every intent type that should have keywords has them."""
        assert IntentType.BUNDLE in INTENT_KEYWORDS
        assert IntentType.RULE in INTENT_KEYWORDS
        assert IntentType.VOICE in INTENT_KEYWORDS
        assert IntentType.IMAGE in INTENT_KEYWORDS
        assert IntentType.CONFIG in INTENT_KEYWORDS
        assert IntentType.SUPPORT in INTENT_KEYWORDS
        assert IntentType.KNOWLEDGE in INTENT_KEYWORDS

    def test_chat_intent_has_no_keywords(self):
        """CHAT is the fallback intent — should NOT have keywords."""
        assert IntentType.CHAT not in INTENT_KEYWORDS
