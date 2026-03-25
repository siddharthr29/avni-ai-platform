"""Tests for the skip logic generator service.

Tests cover:
- Condition parsing (12+ pattern variants)
- Rule generation from parsed conditions
- Concept lookup and UUID resolution
- Missing concept / answer handling
- Batch processing of a mock bundle directory
- Edge cases (empty input, malformed text, case insensitivity)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.skip_logic_generator import (
    ConceptLookup,
    SkipCondition,
    generate_skip_logic_for_bundle,
    generate_skip_logic_rule,
    parse_condition,
    parse_condition_with_llm_fallback,
    _infer_scope,
    _extract_key_value,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONCEPTS: list[dict] = [
    {
        "name": "Pregnancy Status",
        "uuid": "uuid-pregnancy-status",
        "dataType": "Coded",
        "answers": [
            {"name": "Yes", "uuid": "uuid-yes", "order": 0.0},
            {"name": "No", "uuid": "uuid-no", "order": 1.0},
        ],
    },
    {
        "name": "Age",
        "uuid": "uuid-age",
        "dataType": "Numeric",
    },
    {
        "name": "Blood Group",
        "uuid": "uuid-blood-group",
        "dataType": "Coded",
        "answers": [
            {"name": "A+", "uuid": "uuid-a-pos", "order": 0.0},
            {"name": "B+", "uuid": "uuid-b-pos", "order": 1.0},
            {"name": "O+", "uuid": "uuid-o-pos", "order": 2.0},
            {"name": "AB+", "uuid": "uuid-ab-pos", "order": 3.0},
        ],
    },
    {
        "name": "Weight",
        "uuid": "uuid-weight",
        "dataType": "Numeric",
    },
    {
        "name": "Visit Type",
        "uuid": "uuid-visit-type",
        "dataType": "Coded",
        "answers": [
            {"name": "Routine", "uuid": "uuid-routine", "order": 0.0},
            {"name": "Emergency", "uuid": "uuid-emergency", "order": 1.0},
        ],
    },
    {
        "name": "Phone Number",
        "uuid": "uuid-phone",
        "dataType": "Text",
    },
]


@pytest.fixture
def concept_lookup() -> ConceptLookup:
    return ConceptLookup(SAMPLE_CONCEPTS)


@pytest.fixture
def mock_bundle_dir():
    """Create a temporary bundle directory with concepts.json and a form file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write concepts.json
        with open(os.path.join(tmpdir, "concepts.json"), "w") as f:
            json.dump(SAMPLE_CONCEPTS, f)

        # Write a form file with showWhen/hideWhen keyValues
        form_data = {
            "name": "ANC Visit Form",
            "uuid": "form-uuid-1",
            "formType": "Encounter",
            "formElementGroups": [
                {
                    "uuid": "group-uuid-1",
                    "name": "Pregnancy Details",
                    "displayOrder": 1.0,
                    "formElements": [
                        {
                            "name": "Expected Delivery Date",
                            "uuid": "elem-uuid-1",
                            "keyValues": [
                                {"key": "showWhen", "value": "If Pregnancy Status is Yes"},
                            ],
                            "concept": {
                                "name": "Expected Delivery Date",
                                "uuid": "uuid-edd",
                                "dataType": "Date",
                            },
                            "displayOrder": 1.0,
                            "type": "SingleSelect",
                            "mandatory": False,
                        },
                        {
                            "name": "Weight Gain Alert",
                            "uuid": "elem-uuid-2",
                            "keyValues": [
                                {"key": "showWhen", "value": "When Weight > 100"},
                            ],
                            "concept": {
                                "name": "Weight Gain Alert",
                                "uuid": "uuid-weight-alert",
                                "dataType": "Text",
                            },
                            "displayOrder": 2.0,
                            "type": "SingleSelect",
                            "mandatory": False,
                        },
                        {
                            "name": "No Conditions Field",
                            "uuid": "elem-uuid-3",
                            "keyValues": [],
                            "concept": {
                                "name": "No Conditions Field",
                                "uuid": "uuid-no-cond",
                                "dataType": "Text",
                            },
                            "displayOrder": 3.0,
                            "type": "SingleSelect",
                            "mandatory": False,
                        },
                        {
                            "name": "Phone Contact",
                            "uuid": "elem-uuid-4",
                            "keyValues": [
                                {"key": "hideWhen", "value": "If Phone Number is empty"},
                            ],
                            "concept": {
                                "name": "Phone Contact",
                                "uuid": "uuid-phone-contact",
                                "dataType": "Text",
                            },
                            "displayOrder": 4.0,
                            "type": "SingleSelect",
                            "mandatory": False,
                        },
                    ],
                }
            ],
        }
        with open(os.path.join(tmpdir, "anc_form.json"), "w") as f:
            json.dump(form_data, f)

        yield tmpdir


# ---------------------------------------------------------------------------
# Test: parse_condition — basic patterns
# ---------------------------------------------------------------------------


class TestParseCondition:

    def test_if_x_is_yes(self):
        result = parse_condition("If Pregnancy Status is Yes")
        assert result is not None
        assert result.trigger_field == "Pregnancy Status"
        assert result.operator == "equals"
        assert result.value == "Yes"
        assert result.action == "show"

    def test_when_x_equals_value(self):
        result = parse_condition("When Visit Type = Emergency")
        assert result is not None
        assert result.trigger_field == "Visit Type"
        assert result.operator == "equals"
        assert result.value == "Emergency"

    def test_if_x_greater_than(self):
        result = parse_condition("When Age > 5")
        assert result is not None
        assert result.trigger_field == "Age"
        assert result.operator == "greater_than"
        assert result.value == "5"

    def test_if_x_greater_than_decimal(self):
        result = parse_condition("If Weight > 50.5")
        assert result is not None
        assert result.trigger_field == "Weight"
        assert result.operator == "greater_than"
        assert result.value == "50.5"

    def test_if_x_less_than(self):
        result = parse_condition("If Age < 18")
        assert result is not None
        assert result.trigger_field == "Age"
        assert result.operator == "less_than"
        assert result.value == "18"

    def test_if_x_is_not_empty(self):
        result = parse_condition("If Phone Number is not empty")
        assert result is not None
        assert result.trigger_field == "Phone Number"
        assert result.operator == "is_not_empty"
        assert result.value is None

    def test_if_x_is_empty(self):
        result = parse_condition("If Phone Number is empty")
        assert result is not None
        assert result.trigger_field == "Phone Number"
        assert result.operator == "is_empty"
        assert result.value is None

    def test_if_x_is_not_value(self):
        result = parse_condition("If Pregnancy Status is not No")
        assert result is not None
        assert result.trigger_field == "Pregnancy Status"
        assert result.operator == "not_equals"
        assert result.value == "No"

    def test_hide_action_from_text(self):
        result = parse_condition("If Pregnancy Status is No, hide")
        assert result is not None
        assert result.trigger_field == "Pregnancy Status"
        assert result.operator == "equals"
        assert result.value == "No"
        assert result.action == "hide"

    def test_hide_when_prefix(self):
        result = parse_condition("hide if Visit Type is Routine")
        assert result is not None
        assert result.action == "hide"
        assert result.trigger_field == "Visit Type"
        assert result.value == "Routine"

    def test_contains_pattern(self):
        result = parse_condition("If Blood Group contains A+")
        assert result is not None
        assert result.trigger_field == "Blood Group"
        assert result.operator == "contains"
        assert result.value == "A+"

    def test_between_pattern(self):
        result = parse_condition("If Age is between 15 and 49")
        assert result is not None
        assert result.trigger_field == "Age"
        assert result.operator == "between"
        assert result.value == "15,49"

    def test_has_value_pattern(self):
        result = parse_condition("When Weight has a value")
        assert result is not None
        assert result.trigger_field == "Weight"
        assert result.operator == "is_not_empty"

    def test_context_hide(self):
        """When context is 'hide', default action should be hide."""
        result = parse_condition("If Pregnancy Status is Yes", context="hide")
        assert result is not None
        assert result.action == "hide"

    def test_empty_input(self):
        assert parse_condition("") is None
        assert parse_condition("   ") is None
        assert parse_condition(None) is None  # type: ignore[arg-type]

    def test_unparseable_text(self):
        result = parse_condition("something random with no pattern match at all blah")
        assert result is None

    def test_case_insensitivity(self):
        result = parse_condition("IF PREGNANCY STATUS IS YES")
        assert result is not None
        assert result.trigger_field == "PREGNANCY STATUS"
        assert result.value == "YES"

    def test_bracket_field_names(self):
        result = parse_condition("If [Pregnancy Status] is [Yes]")
        assert result is not None
        assert result.trigger_field == "Pregnancy Status"
        assert result.value == "Yes"

    def test_bare_field_reference(self):
        """'If Weight' should become is_not_empty check."""
        result = parse_condition("If Weight")
        assert result is not None
        assert result.trigger_field == "Weight"
        assert result.operator == "is_not_empty"


# ---------------------------------------------------------------------------
# Test: ConceptLookup
# ---------------------------------------------------------------------------


class TestConceptLookup:

    def test_find_concept(self, concept_lookup: ConceptLookup):
        c = concept_lookup.find_concept("Pregnancy Status")
        assert c is not None
        assert c["uuid"] == "uuid-pregnancy-status"

    def test_find_concept_case_insensitive(self, concept_lookup: ConceptLookup):
        c = concept_lookup.find_concept("pregnancy status")
        assert c is not None

    def test_find_concept_missing(self, concept_lookup: ConceptLookup):
        assert concept_lookup.find_concept("Nonexistent Field") is None

    def test_find_answer_uuid(self, concept_lookup: ConceptLookup):
        uuid = concept_lookup.find_answer_uuid("Pregnancy Status", "Yes")
        assert uuid == "uuid-yes"

    def test_find_answer_uuid_missing(self, concept_lookup: ConceptLookup):
        uuid = concept_lookup.find_answer_uuid("Pregnancy Status", "Maybe")
        assert uuid is None

    def test_find_concept_uuid(self, concept_lookup: ConceptLookup):
        assert concept_lookup.find_concept_uuid("Age") == "uuid-age"

    def test_find_concept_data_type(self, concept_lookup: ConceptLookup):
        assert concept_lookup.find_concept_data_type("Age") == "Numeric"
        assert concept_lookup.find_concept_data_type("Pregnancy Status") == "Coded"


# ---------------------------------------------------------------------------
# Test: generate_skip_logic_rule
# ---------------------------------------------------------------------------


class TestGenerateRule:

    def test_coded_equals_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Pregnancy Status",
            operator="equals",
            value="Yes",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        assert "declarativeRule" in rule
        dr = rule["declarativeRule"][0]
        assert dr["actions"][0]["actionType"] == "showFormElement"
        lhs = dr["conditions"][0]["compoundRule"]["rules"][0]["lhs"]
        assert lhs["conceptName"] == "Pregnancy Status"
        assert lhs["conceptUuid"] == "uuid-pregnancy-status"
        rhs = dr["conditions"][0]["compoundRule"]["rules"][0]["rhs"]
        assert rhs["answerConceptNames"] == ["Yes"]
        assert rhs["answerConceptUuids"] == ["uuid-yes"]

    def test_hide_action_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Pregnancy Status",
            operator="equals",
            value="No",
            action="hide",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        assert rule["declarativeRule"][0]["actions"][0]["actionType"] == "hideFormElement"

    def test_numeric_greater_than_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Weight",
            operator="greater_than",
            value="100",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        r = rule["declarativeRule"][0]["conditions"][0]["compoundRule"]["rules"][0]
        assert r["operator"] == "greaterThan"
        assert r["rhs"]["value"] == "100"
        assert r["lhs"]["conceptDataType"] == "Numeric"

    def test_existence_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Phone Number",
            operator="is_not_empty",
            value=None,
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        r = rule["declarativeRule"][0]["conditions"][0]["compoundRule"]["rules"][0]
        assert r["operator"] == "defined"

    def test_is_empty_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Phone Number",
            operator="is_empty",
            value=None,
            action="hide",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        r = rule["declarativeRule"][0]["conditions"][0]["compoundRule"]["rules"][0]
        assert r["operator"] == "notDefined"

    def test_between_rule(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Age",
            operator="between",
            value="15,49",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is not None
        rules = rule["declarativeRule"][0]["conditions"][0]["compoundRule"]["rules"]
        assert len(rules) == 2
        assert rules[0]["operator"] == "greaterThan"
        assert rules[0]["rhs"]["value"] == "15"
        assert rules[1]["operator"] == "lessThan"
        assert rules[1]["rhs"]["value"] == "49"

    def test_missing_concept_returns_none(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Nonexistent Field",
            operator="equals",
            value="Yes",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is None

    def test_missing_answer_returns_none(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Pregnancy Status",
            operator="equals",
            value="Maybe",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is None

    def test_equals_without_value_returns_none(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Pregnancy Status",
            operator="equals",
            value=None,
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup)
        assert rule is None

    def test_custom_scope(self, concept_lookup: ConceptLookup):
        condition = SkipCondition(
            trigger_field="Pregnancy Status",
            operator="equals",
            value="Yes",
            action="show",
        )
        rule = generate_skip_logic_rule(condition, concept_lookup, scope="programEnrolment")
        assert rule is not None
        lhs = rule["declarativeRule"][0]["conditions"][0]["compoundRule"]["rules"][0]["lhs"]
        assert lhs["scope"] == "programEnrolment"


# ---------------------------------------------------------------------------
# Test: Scope inference
# ---------------------------------------------------------------------------


class TestInferScope:

    def test_encounter(self):
        assert _infer_scope("Encounter") == "encounter"

    def test_registration(self):
        assert _infer_scope("IndividualProfile") == "registration"

    def test_enrolment(self):
        assert _infer_scope("ProgramEnrolment") == "programEnrolment"

    def test_exit(self):
        assert _infer_scope("ProgramExit") == "programExit"

    def test_none(self):
        assert _infer_scope(None) == "encounter"


# ---------------------------------------------------------------------------
# Test: Helper utilities
# ---------------------------------------------------------------------------


class TestHelpers:

    def test_extract_key_value(self):
        kvs = [{"key": "showWhen", "value": "If X is Y"}, {"key": "other", "value": "z"}]
        assert _extract_key_value(kvs, "showWhen") == "If X is Y"
        assert _extract_key_value(kvs, "hideWhen") is None
        assert _extract_key_value([], "showWhen") is None

    def test_skip_condition_to_dict(self):
        c = SkipCondition("Field", "equals", "Yes", "show")
        d = c.to_dict()
        assert d == {
            "trigger_field": "Field",
            "operator": "equals",
            "value": "Yes",
            "action": "show",
        }


# ---------------------------------------------------------------------------
# Test: Batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:

    @pytest.mark.asyncio
    async def test_generate_skip_logic_for_bundle(self, mock_bundle_dir: str):
        result = await generate_skip_logic_for_bundle(mock_bundle_dir)

        # "If Pregnancy Status is Yes" should succeed
        # "When Weight > 100" should succeed (numeric)
        # "If Phone Number is empty" should succeed (existence)
        assert result["rules_generated"] >= 2
        assert result["parse_failed"] == 0

        # Verify the form file was updated
        form_path = Path(mock_bundle_dir) / "anc_form.json"
        with open(form_path, "r") as f:
            updated = json.load(f)

        # First element should have a rule attached
        elem1 = updated["formElementGroups"][0]["formElements"][0]
        assert "rule" in elem1
        rule_data = json.loads(elem1["rule"])
        assert "declarativeRule" in rule_data

    @pytest.mark.asyncio
    async def test_bundle_missing_concepts_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await generate_skip_logic_for_bundle(tmpdir)
            assert result["rules_generated"] == 0
            assert len(result["details"]) == 1
            assert "not found" in result["details"][0]["error"]

    @pytest.mark.asyncio
    async def test_bundle_no_form_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Only concepts.json, no forms
            with open(os.path.join(tmpdir, "concepts.json"), "w") as f:
                json.dump(SAMPLE_CONCEPTS, f)
            result = await generate_skip_logic_for_bundle(tmpdir)
            assert result["rules_generated"] == 0
            assert result["rules_failed"] == 0

    @pytest.mark.asyncio
    async def test_bundle_element_without_key_values(self, mock_bundle_dir: str):
        """Element with empty keyValues should be skipped without error."""
        result = await generate_skip_logic_for_bundle(mock_bundle_dir)
        # The "No Conditions Field" element has no showWhen/hideWhen
        no_cond_details = [
            d for d in result["details"] if d.get("element") == "No Conditions Field"
        ]
        assert len(no_cond_details) == 0  # Not processed at all


# ---------------------------------------------------------------------------
# Test: LLM fallback (mocked)
# ---------------------------------------------------------------------------


class TestLLMFallback:

    @pytest.mark.asyncio
    async def test_llm_fallback_on_unparseable(self):
        """When regex fails, the LLM fallback should be attempted."""
        mock_response = json.dumps({
            "trigger_field": "Custom Field",
            "operator": "equals",
            "value": "Special",
            "action": "show",
        })

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(return_value=mock_response)

        with patch.dict(
            "sys.modules",
            {"app.services.claude_client": type("M", (), {"claude_client": mock_client})()},
        ):
            result = await parse_condition_with_llm_fallback(
                "Display this when Custom Field has Special selected"
            )

        assert result is not None
        assert result.trigger_field == "Custom Field"
        assert result.operator == "equals"
        assert result.value == "Special"

    @pytest.mark.asyncio
    async def test_llm_fallback_failure_returns_none(self):
        """When both regex and LLM fail, return None."""
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        with patch.dict(
            "sys.modules",
            {"app.services.claude_client": type("M", (), {"claude_client": mock_client})()},
        ):
            result = await parse_condition_with_llm_fallback(
                "completely unparseable gibberish xyz 123"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_regex_match_skips_llm(self):
        """When regex succeeds, LLM should not be called."""
        mock_client = AsyncMock()
        mock_client.complete = AsyncMock()

        with patch.dict(
            "sys.modules",
            {"app.services.claude_client": type("M", (), {"claude_client": mock_client})()},
        ):
            result = await parse_condition_with_llm_fallback("If Age > 10")

        assert result is not None
        assert result.operator == "greater_than"
        mock_client.complete.assert_not_called()
