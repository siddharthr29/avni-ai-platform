"""Tests for support diagnosis service.

Covers:
- Pattern matching for common Avni issues
- Keyword scoring
- Diagnosis structure
- Claude AI fallback
- Edge cases
"""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.support_diagnosis import diagnose, _match_patterns


# ── Pattern Matching ─────────────────────────────────────────────────────────


class TestPatternMatching:
    def test_sync_issue_detected(self):
        matches = _match_patterns("data is not syncing on mobile app")
        assert len(matches) > 0
        patterns = [m[0]["pattern"] for m in matches]
        assert any("sync" in p for p in patterns)

    def test_form_not_showing_detected(self):
        matches = _match_patterns("form not showing in the app")
        assert len(matches) > 0

    def test_upload_error_detected(self):
        matches = _match_patterns("upload failed when importing bundle")
        assert len(matches) > 0

    def test_clean_text_low_scores(self):
        matches = _match_patterns("how to create a new program in Avni")
        # May match some keywords but with low confidence
        if matches:
            assert matches[0][1] < 0.5

    def test_returns_sorted_by_score(self):
        matches = _match_patterns("sync error not working sync failed")
        if len(matches) > 1:
            assert matches[0][1] >= matches[1][1]


# ── Diagnose Function ───────────────────────────────────────────────────────


class TestDiagnose:
    @pytest.mark.asyncio
    async def test_sync_diagnosis(self):
        with patch("app.services.support_diagnosis.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"pattern": "sync", "confidence": 0.9}')
            result = await diagnose("my app is not syncing data")
            assert "pattern" in result
            assert "diagnosis" in result
            assert "common_fixes" in result
            assert "confidence" in result

    @pytest.mark.asyncio
    async def test_diagnosis_with_error_message(self):
        with patch("app.services.support_diagnosis.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"pattern": "sync", "confidence": 0.8}')
            result = await diagnose(
                "sync failing",
                error_message="ConnectionTimeout: Server unreachable"
            )
            assert result["confidence"] > 0

    @pytest.mark.asyncio
    async def test_diagnosis_result_structure(self):
        with patch("app.services.support_diagnosis.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value='{"pattern": "sync", "confidence": 0.9}')
            result = await diagnose("sync is broken")
            # Should have all required keys
            assert "pattern" in result
            assert "diagnosis" in result
            assert "checks" in result
            assert "common_fixes" in result
            assert "confidence" in result

    @pytest.mark.asyncio
    async def test_unknown_issue_handled(self):
        """Unknown issues should still return a result."""
        with patch("app.services.support_diagnosis.claude_client") as mock_client:
            mock_client.complete = AsyncMock(
                return_value='{"pattern": "unknown", "confidence": 0.3, "ai_analysis": "General issue"}'
            )
            result = await diagnose("something random is happening with my system")
            assert result is not None

    @pytest.mark.asyncio
    async def test_claude_failure_still_returns_result(self):
        """If Claude fails, should still return keyword-based result."""
        with patch("app.services.support_diagnosis.claude_client") as mock_client:
            mock_client.complete = AsyncMock(side_effect=Exception("API Error"))
            result = await diagnose("sync error on mobile")
            assert result is not None
            assert "pattern" in result
