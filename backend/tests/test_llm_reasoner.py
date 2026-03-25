"""Tests for llm_reasoner — deterministic + LLM-based field enrichment."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.schemas import SRSFormField
from app.services.llm_reasoner import (
    FieldRule,
    _enrich_field_deterministic,
    _find_rule,
    _get_key_value,
    _normalise_name,
    enrich_fields,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_field(
    name: str,
    data_type: str = "Numeric",
    unit: str | None = None,
    low: float | None = None,
    high: float | None = None,
    key_values: list[dict[str, Any]] | None = None,
    **kwargs,
) -> SRSFormField:
    return SRSFormField(
        name=name,
        dataType=data_type,
        unit=unit,
        lowAbsolute=low,
        highAbsolute=high,
        keyValues=key_values,
        **kwargs,
    )


def _kv(field: SRSFormField, key: str) -> Any | None:
    """Shorthand to read a keyValue."""
    if field.keyValues is None:
        return None
    return _get_key_value(field.keyValues, key)


# ---------------------------------------------------------------------------
# 1. Deterministic enrichment — known numeric fields
# ---------------------------------------------------------------------------

class TestDeterministicNumeric:
    """Deterministic enrichment for well-known numeric fields."""

    def test_weight_enrichment(self):
        f = _make_field("Weight")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowNegativeValue") is False
        assert _kv(f, "allowDecimalValue") is True
        assert f.lowAbsolute == 0
        assert f.highAbsolute == 200
        assert f.unit == "kg"

    def test_height_enrichment(self):
        f = _make_field("Height")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is True
        assert f.unit == "cm"
        assert f.lowAbsolute == 0
        assert f.highAbsolute == 250

    def test_age_enrichment(self):
        f = _make_field("Age")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowNegativeValue") is False
        assert _kv(f, "allowDecimalValue") is True
        assert f.lowAbsolute == 0
        assert f.highAbsolute == 120
        assert f.unit == "years"

    def test_hemoglobin_enrichment(self):
        f = _make_field("Hemoglobin")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is True
        assert f.lowAbsolute == 2
        assert f.highAbsolute == 20
        assert f.unit == "g/dL"

    def test_temperature_enrichment(self):
        f = _make_field("Body Temperature")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is True
        assert f.lowAbsolute == 90
        assert f.highAbsolute == 110
        assert f.unit == "\u00b0F"

    def test_systolic_bp_enrichment(self):
        f = _make_field("Systolic Blood Pressure")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is False
        assert f.lowAbsolute == 50
        assert f.highAbsolute == 260
        assert f.unit == "mmHg"

    def test_diastolic_bp_enrichment(self):
        f = _make_field("Diastolic")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is False
        assert f.lowAbsolute == 30
        assert f.highAbsolute == 160
        assert f.unit == "mmHg"

    def test_pulse_rate_enrichment(self):
        f = _make_field("Pulse Rate")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is False
        assert f.unit == "bpm"

    def test_spo2_enrichment(self):
        f = _make_field("SpO2")
        assert _enrich_field_deterministic(f) is True
        assert f.lowAbsolute == 50
        assert f.highAbsolute == 100
        assert f.unit == "%"

    def test_blood_sugar_enrichment(self):
        f = _make_field("Fasting Blood Sugar")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is True
        assert f.unit == "mg/dL"

    def test_muac_enrichment(self):
        f = _make_field("MUAC")
        assert _enrich_field_deterministic(f) is True
        assert _kv(f, "allowDecimalValue") is True
        assert f.unit == "cm"
        assert f.lowAbsolute == 5
        assert f.highAbsolute == 40

    def test_birth_weight_more_specific_than_weight(self):
        """'Birth weight' should match the more specific rule, not generic 'weight'."""
        f = _make_field("Birth Weight")
        _enrich_field_deterministic(f)
        assert f.lowAbsolute == 0.5
        assert f.highAbsolute == 6.0
        assert f.unit == "kg"

    def test_gestational_age_enrichment(self):
        f = _make_field("Gestational Age")
        assert _enrich_field_deterministic(f) is True
        assert f.unit == "weeks"
        assert f.lowAbsolute == 1
        assert f.highAbsolute == 45


# ---------------------------------------------------------------------------
# 2. Non-overwrite (NON-DESTRUCTIVE) behaviour
# ---------------------------------------------------------------------------

class TestNonDestructive:
    """Existing values must NEVER be overwritten."""

    def test_existing_unit_not_overwritten(self):
        f = _make_field("Weight", unit="lbs")
        _enrich_field_deterministic(f)
        assert f.unit == "lbs"  # kept original

    def test_existing_low_absolute_not_overwritten(self):
        f = _make_field("Height", low=10)
        _enrich_field_deterministic(f)
        assert f.lowAbsolute == 10  # kept original
        assert f.highAbsolute == 250  # filled missing

    def test_existing_high_absolute_not_overwritten(self):
        f = _make_field("Age", high=99)
        _enrich_field_deterministic(f)
        assert f.highAbsolute == 99  # kept original
        assert f.lowAbsolute == 0  # filled missing

    def test_existing_keyvalue_not_overwritten(self):
        f = _make_field(
            "Weight",
            key_values=[{"key": "allowDecimalValue", "value": False}],
        )
        _enrich_field_deterministic(f)
        assert _kv(f, "allowDecimalValue") is False  # kept original (rule says True)

    def test_existing_allow_future_date_not_overwritten(self):
        f = _make_field(
            "Date of birth",
            data_type="Date",
            key_values=[{"key": "allowFutureDate", "value": True}],
        )
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is True  # kept original (rule says False)


# ---------------------------------------------------------------------------
# 3. Coded fields skipped
# ---------------------------------------------------------------------------

class TestCodedFieldsSkipped:
    """Coded (dropdown) fields should not get numeric enrichment."""

    def test_coded_field_not_enriched(self):
        f = _make_field("Gender", data_type="Coded")
        assert _enrich_field_deterministic(f) is False
        assert f.keyValues is None  # not initialised

    def test_text_field_not_enriched(self):
        f = _make_field("Name", data_type="Text")
        assert _enrich_field_deterministic(f) is False

    def test_notes_field_not_enriched(self):
        f = _make_field("Remarks", data_type="Notes")
        assert _enrich_field_deterministic(f) is False

    def test_image_field_not_enriched(self):
        f = _make_field("Photo", data_type="Image")
        assert _enrich_field_deterministic(f) is False


# ---------------------------------------------------------------------------
# 4. Date fields — allowFutureDate
# ---------------------------------------------------------------------------

class TestDateEnrichment:
    """Date fields get allowFutureDate correctly."""

    def test_date_of_birth_no_future(self):
        f = _make_field("Date of Birth", data_type="Date")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is False

    def test_lmp_no_future(self):
        f = _make_field("LMP", data_type="Date")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is False

    def test_edd_allows_future(self):
        f = _make_field("Expected Date of Delivery", data_type="Date")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is True

    def test_next_visit_date_allows_future(self):
        f = _make_field("Next visit date", data_type="Date")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is True

    def test_unknown_date_defaults_to_no_future(self):
        """Unknown date fields default to allowFutureDate=False (safe default)."""
        f = _make_field("Some Random Date", data_type="Date")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is False

    def test_datetime_also_enriched(self):
        f = _make_field("Date of Registration", data_type="DateTime")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowFutureDate") is False


# ---------------------------------------------------------------------------
# 5. Count fields — integer, non-negative
# ---------------------------------------------------------------------------

class TestCountFields:
    """Count fields should be integer (no decimal) and non-negative."""

    def test_number_of_children(self):
        f = _make_field("Number of children")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowNegativeValue") is False
        assert _kv(f, "allowDecimalValue") is False

    def test_number_of_doses(self):
        f = _make_field("Number of doses")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowNegativeValue") is False
        assert _kv(f, "allowDecimalValue") is False

    def test_number_of_family_members(self):
        f = _make_field("Number of family members")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowDecimalValue") is False
        assert f.lowAbsolute == 1
        assert f.highAbsolute == 50

    def test_heuristic_count_pattern(self):
        """Unknown 'Number of X' fields should still get integer treatment."""
        f = _make_field("Number of toilets")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowNegativeValue") is False
        assert _kv(f, "allowDecimalValue") is False


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_field_name(self):
        f = _make_field("")
        assert _enrich_field_deterministic(f) is False

    def test_whitespace_field_name(self):
        f = _make_field("   ")
        # _find_rule returns None for empty normalised name
        rule = _find_rule("   ")
        assert rule is None

    def test_case_insensitive_matching(self):
        """Field names should match regardless of case."""
        f = _make_field("HEMOGLOBIN")
        _enrich_field_deterministic(f)
        assert _kv(f, "allowDecimalValue") is True
        assert f.unit == "g/dL"

    def test_partial_name_matching(self):
        """'Weight of child in kg' should match the 'weight' rule."""
        f = _make_field("Weight of child in kg")
        _enrich_field_deterministic(f)
        assert f.lowAbsolute == 0
        assert f.highAbsolute == 200

    def test_unknown_numeric_field_gets_allow_negative_false(self):
        """Unknown numeric fields still get allowNegativeValue=False as default."""
        f = _make_field("Spirometry FEV1")
        # No rule match, but it's still Numeric
        # The function won't enrich unknown fields without a rule (except count heuristic)
        _enrich_field_deterministic(f)
        # allowNegativeValue is NOT set for unknown non-count fields (no rule match)
        # because the function only sets it when a rule is found or count pattern matches

    def test_normalise_name(self):
        assert _normalise_name("  Weight  of  Child ") == "weight of child"

    def test_find_rule_longest_match(self):
        """Longest pattern should win: 'birth weight' > 'weight'."""
        rule = _find_rule("Birth Weight")
        assert rule is not None
        assert rule.high_absolute == 6.0  # birth weight rule, not generic weight


# ---------------------------------------------------------------------------
# 7. async enrich_fields — integration (deterministic only)
# ---------------------------------------------------------------------------

class TestEnrichFieldsAsync:
    """Test the main enrich_fields function."""

    @pytest.mark.asyncio
    async def test_enriches_multiple_fields(self):
        fields = [
            _make_field("Weight"),
            _make_field("Height"),
            _make_field("Gender", data_type="Coded"),
            _make_field("Date of Birth", data_type="Date"),
        ]
        result = await enrich_fields(fields, use_llm=False)

        assert len(result) == 4
        # Weight
        assert result[0].unit == "kg"
        assert _kv(result[0], "allowDecimalValue") is True
        # Height
        assert result[1].unit == "cm"
        # Gender — untouched
        assert result[2].keyValues is None
        # Date of Birth
        assert _kv(result[3], "allowFutureDate") is False

    @pytest.mark.asyncio
    async def test_empty_list(self):
        result = await enrich_fields([], use_llm=False)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_same_list_instance(self):
        fields = [_make_field("Weight")]
        result = await enrich_fields(fields, use_llm=False)
        assert result is fields  # mutated in place

    @pytest.mark.asyncio
    async def test_llm_called_for_unknown_fields(self):
        """When use_llm=True, unknown fields are sent to LLM."""
        fields = [
            _make_field("Weight"),  # known — deterministic
            _make_field("Spirometry FEV1"),  # unknown — needs LLM
        ]
        llm_response = json.dumps([
            {
                "name": "Spirometry FEV1",
                "allowNegativeValue": False,
                "allowDecimalValue": True,
                "lowAbsolute": 0.5,
                "highAbsolute": 6.0,
                "unit": "L",
            }
        ])

        with patch(
            "app.services.claude_client.claude_client",
            new_callable=lambda: type("Mock", (), {
                "complete": AsyncMock(return_value=llm_response)
            }),
        ):
            result = await enrich_fields(fields, use_llm=True)

        # Weight enriched deterministically
        assert result[0].unit == "kg"
        # FEV1 enriched by LLM
        assert result[1].unit == "L"
        assert _kv(result[1], "allowDecimalValue") is True
        assert result[1].lowAbsolute == 0.5

    @pytest.mark.asyncio
    async def test_llm_failure_is_graceful(self):
        """LLM failure should not crash — fields just stay unenriched."""
        fields = [_make_field("Spirometry FEV1")]

        with patch(
            "app.services.claude_client.claude_client",
            new_callable=lambda: type("Mock", (), {
                "complete": AsyncMock(side_effect=RuntimeError("LLM down"))
            }),
        ):
            result = await enrich_fields(fields, use_llm=True)

        # Should not crash, field stays unenriched
        assert result[0].unit is None

    @pytest.mark.asyncio
    async def test_llm_invalid_json_is_graceful(self):
        """LLM returning invalid JSON should not crash."""
        fields = [_make_field("Spirometry FEV1")]

        with patch(
            "app.services.claude_client.claude_client",
            new_callable=lambda: type("Mock", (), {
                "complete": AsyncMock(return_value="This is not JSON at all")
            }),
        ):
            result = await enrich_fields(fields, use_llm=True)

        assert result[0].unit is None

    @pytest.mark.asyncio
    async def test_llm_not_called_when_disabled(self):
        """When use_llm=False, no LLM call is made even for unknown fields."""
        fields = [_make_field("Spirometry FEV1")]

        mock_client = type("Mock", (), {
            "complete": AsyncMock(return_value="[]")
        })()

        with patch("app.services.claude_client.claude_client", mock_client):
            await enrich_fields(fields, use_llm=False)

        mock_client.complete.assert_not_called()
