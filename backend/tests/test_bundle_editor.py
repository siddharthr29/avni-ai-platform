"""Tests for the bundle editor service.

Covers:
- Deterministic command parsing (rename, add, remove, make mandatory, etc.)
- Applying edits to concepts.json and form files on disk
- Edge cases (field not found, bundle not found, duplicate concepts)
"""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.services.bundle_editor import (
    BundleEditCommand,
    _try_deterministic_parse,
    apply_edit,
    edit_bundle_nl,
    parse_edit_command,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bundle_path(tmp_path):
    """Create a realistic bundle directory with concepts and forms."""
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir()

    concepts = [
        {
            "name": "Weight",
            "uuid": "uuid-weight",
            "dataType": "Numeric",
            "active": True,
            "unit": "kg",
        },
        {
            "name": "Gender",
            "uuid": "uuid-gender",
            "dataType": "Coded",
            "active": True,
            "answers": [
                {"name": "Male", "uuid": "uuid-male", "order": 0.0},
                {"name": "Female", "uuid": "uuid-female", "order": 1.0},
            ],
        },
        {"name": "Male", "uuid": "uuid-male", "dataType": "NA", "active": True},
        {"name": "Female", "uuid": "uuid-female", "dataType": "NA", "active": True},
        {
            "name": "Caste",
            "uuid": "uuid-caste",
            "dataType": "Coded",
            "active": True,
            "answers": [
                {"name": "SC", "uuid": "uuid-sc", "order": 0.0},
                {"name": "ST", "uuid": "uuid-st", "order": 1.0},
                {"name": "OBC", "uuid": "uuid-obc", "order": 2.0},
            ],
        },
        {"name": "SC", "uuid": "uuid-sc", "dataType": "NA", "active": True},
        {"name": "ST", "uuid": "uuid-st", "dataType": "NA", "active": True},
        {"name": "OBC", "uuid": "uuid-obc", "dataType": "NA", "active": True},
        {
            "name": "Phone Number",
            "uuid": "uuid-phone",
            "dataType": "PhoneNumber",
            "active": True,
        },
        {
            "name": "Age",
            "uuid": "uuid-age",
            "dataType": "Text",
            "active": True,
        },
    ]

    form_registration = {
        "name": "Registration",
        "uuid": "form-reg",
        "formType": "IndividualProfile",
        "formElementGroups": [
            {
                "uuid": "feg-1",
                "name": "Basic Details",
                "displayOrder": 1.0,
                "formElements": [
                    {
                        "name": "Weight",
                        "uuid": "fe-weight",
                        "keyValues": [],
                        "concept": {
                            "name": "Weight",
                            "uuid": "uuid-weight",
                            "dataType": "Numeric",
                            "answers": [],
                            "active": True,
                            "media": [],
                        },
                        "displayOrder": 1.0,
                        "type": "Numeric",
                        "mandatory": True,
                    },
                    {
                        "name": "Gender",
                        "uuid": "fe-gender",
                        "keyValues": [],
                        "concept": {
                            "name": "Gender",
                            "uuid": "uuid-gender",
                            "dataType": "Coded",
                            "answers": [
                                {
                                    "name": "Male",
                                    "uuid": "uuid-male",
                                    "dataType": "NA",
                                    "answers": [],
                                    "order": 0.0,
                                    "active": True,
                                    "media": [],
                                },
                                {
                                    "name": "Female",
                                    "uuid": "uuid-female",
                                    "dataType": "NA",
                                    "answers": [],
                                    "order": 1.0,
                                    "active": True,
                                    "media": [],
                                },
                            ],
                            "active": True,
                            "media": [],
                        },
                        "displayOrder": 2.0,
                        "type": "SingleSelect",
                        "mandatory": True,
                    },
                    {
                        "name": "Phone Number",
                        "uuid": "fe-phone",
                        "keyValues": [],
                        "concept": {
                            "name": "Phone Number",
                            "uuid": "uuid-phone",
                            "dataType": "PhoneNumber",
                            "answers": [],
                            "active": True,
                            "media": [],
                        },
                        "displayOrder": 3.0,
                        "type": "PhoneNumber",
                        "mandatory": False,
                    },
                    {
                        "name": "Age",
                        "uuid": "fe-age",
                        "keyValues": [],
                        "concept": {
                            "name": "Age",
                            "uuid": "uuid-age",
                            "dataType": "Text",
                            "answers": [],
                            "active": True,
                            "media": [],
                        },
                        "displayOrder": 4.0,
                        "type": "Text",
                        "mandatory": False,
                    },
                    {
                        "name": "Caste",
                        "uuid": "fe-caste",
                        "keyValues": [],
                        "concept": {
                            "name": "Caste",
                            "uuid": "uuid-caste",
                            "dataType": "Coded",
                            "answers": [
                                {"name": "SC", "uuid": "uuid-sc", "dataType": "NA", "answers": [], "order": 0.0, "active": True, "media": []},
                                {"name": "ST", "uuid": "uuid-st", "dataType": "NA", "answers": [], "order": 1.0, "active": True, "media": []},
                                {"name": "OBC", "uuid": "uuid-obc", "dataType": "NA", "answers": [], "order": 2.0, "active": True, "media": []},
                            ],
                            "active": True,
                            "media": [],
                        },
                        "displayOrder": 5.0,
                        "type": "SingleSelect",
                        "mandatory": False,
                    },
                ],
            },
        ],
    }

    (tmp_path / "concepts.json").write_text(json.dumps(concepts, indent=2))
    (forms_dir / "Registration.json").write_text(json.dumps(form_registration, indent=2))

    return tmp_path


@pytest.fixture
def bundle_id(bundle_path):
    """Return the bundle directory name as bundle_id."""
    return bundle_path.name


# ---------------------------------------------------------------------------
# Deterministic Parsing Tests
# ---------------------------------------------------------------------------

class TestDeterministicParsing:
    """Tests for regex-based deterministic parsing."""

    def test_parse_rename_single_quotes(self):
        result = _try_deterministic_parse("rename field 'Weight' to 'Body Weight'")
        assert result is not None
        assert len(result) == 1
        cmd = result[0]
        assert cmd.action == "rename_field"
        assert cmd.target_field == "Weight"
        assert cmd.params["new_name"] == "Body Weight"

    def test_parse_rename_double_quotes(self):
        result = _try_deterministic_parse('rename "Weight" to "Body Weight"')
        assert result is not None
        assert result[0].action == "rename_field"
        assert result[0].target_field == "Weight"
        assert result[0].params["new_name"] == "Body Weight"

    def test_parse_add_field_with_options(self):
        result = _try_deterministic_parse(
            "add field 'Blood Group' with options A+, A-, B+, B-, O+, O-, AB+, AB-"
        )
        assert result is not None
        cmd = result[0]
        assert cmd.action == "add_field"
        assert cmd.target_field == "Blood Group"
        assert cmd.params["data_type"] == "Coded"
        assert "A+" in cmd.params["options"]
        assert "AB-" in cmd.params["options"]
        assert len(cmd.params["options"]) == 8

    def test_parse_add_field_typed(self):
        result = _try_deterministic_parse("add field 'Height' as Numeric")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "add_field"
        assert cmd.target_field == "Height"
        assert cmd.params["data_type"] == "Numeric"

    def test_parse_add_field_simple(self):
        result = _try_deterministic_parse("add field 'Notes'")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "add_field"
        assert cmd.target_field == "Notes"
        assert cmd.params["data_type"] == "Text"

    def test_parse_remove_field(self):
        result = _try_deterministic_parse("remove field 'Caste'")
        assert result is not None
        assert result[0].action == "remove_field"
        assert result[0].target_field == "Caste"

    def test_parse_delete_field(self):
        result = _try_deterministic_parse("delete 'Caste'")
        assert result is not None
        assert result[0].action == "remove_field"

    def test_parse_make_mandatory(self):
        result = _try_deterministic_parse("make 'Phone Number' mandatory")
        assert result is not None
        assert result[0].action == "make_mandatory"
        assert result[0].target_field == "Phone Number"

    def test_parse_make_optional(self):
        result = _try_deterministic_parse("make 'Weight' optional")
        assert result is not None
        assert result[0].action == "make_optional"
        assert result[0].target_field == "Weight"

    def test_parse_change_type(self):
        result = _try_deterministic_parse("change data type of 'Age' to Numeric")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "change_type"
        assert cmd.target_field == "Age"
        assert cmd.params["new_type"] == "Numeric"

    def test_parse_change_type_shorthand(self):
        result = _try_deterministic_parse("change type of 'Age' to Numeric")
        assert result is not None
        assert result[0].action == "change_type"

    def test_parse_add_option(self):
        result = _try_deterministic_parse("add option 'Other' to 'Referral Reason'")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "add_option"
        assert cmd.target_field == "Referral Reason"
        assert cmd.params["options"] == ["Other"]

    def test_parse_add_multiple_options(self):
        result = _try_deterministic_parse("add options 'Other', 'Unknown' to 'Gender'")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "add_option"
        assert len(cmd.params["options"]) == 2

    def test_parse_remove_option(self):
        result = _try_deterministic_parse("remove option 'OBC' from 'Caste'")
        assert result is not None
        cmd = result[0]
        assert cmd.action == "remove_option"
        assert cmd.target_field == "Caste"
        assert cmd.params["options"] == ["OBC"]

    def test_parse_no_match_returns_none(self):
        result = _try_deterministic_parse("do something weird")
        assert result is None

    def test_parse_empty_returns_none(self):
        result = _try_deterministic_parse("")
        assert result is None


# ---------------------------------------------------------------------------
# Apply Edit Tests — Rename
# ---------------------------------------------------------------------------

class TestApplyRename:
    """Tests for applying rename edits."""

    def test_rename_updates_concepts_json(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="rename_field",
                target_field="Weight",
                params={"new_name": "Body Weight"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True
        assert any("concepts.json" in c for c in result["changes"])

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        names = [c["name"] for c in concepts]
        assert "Body Weight" in names
        assert "Weight" not in names

    def test_rename_updates_form_files(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="rename_field",
                target_field="Weight",
                params={"new_name": "Body Weight"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        weight_el = next(
            (e for e in elements if e["concept"]["name"] == "Body Weight"), None
        )
        assert weight_el is not None
        assert weight_el["name"] == "Body Weight"

    def test_rename_field_not_found(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="rename_field",
                target_field="Nonexistent Field",
                params={"new_name": "Something"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Apply Edit Tests — Add Field
# ---------------------------------------------------------------------------

class TestApplyAddField:
    """Tests for applying add field edits."""

    def test_add_field_to_concepts(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="add_field",
                target_field="Height",
                params={"data_type": "Numeric"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True
        concepts = json.loads((bundle_path / "concepts.json").read_text())
        height = next((c for c in concepts if c["name"] == "Height"), None)
        assert height is not None
        assert height["dataType"] == "Numeric"
        assert height["uuid"]  # UUID was generated

    def test_add_coded_field_with_options(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="add_field",
                target_field="Blood Group",
                target_form="Registration",
                params={"data_type": "Coded", "options": ["A+", "B+", "O+"]},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        bg = next((c for c in concepts if c["name"] == "Blood Group"), None)
        assert bg is not None
        assert bg["dataType"] == "Coded"
        assert len(bg["answers"]) == 3

        # Verify answer concepts were created
        a_plus = next((c for c in concepts if c["name"] == "A+"), None)
        assert a_plus is not None
        assert a_plus["dataType"] == "NA"

        # Verify form was updated
        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        bg_el = next(
            (e for e in elements if e["concept"]["name"] == "Blood Group"), None
        )
        assert bg_el is not None
        assert bg_el["type"] == "SingleSelect"

    def test_add_duplicate_field_fails(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="add_field",
                target_field="Weight",
                params={"data_type": "Numeric"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False
        assert "already exists" in result["error"]


# ---------------------------------------------------------------------------
# Apply Edit Tests — Remove Field
# ---------------------------------------------------------------------------

class TestApplyRemoveField:
    """Tests for applying remove field edits."""

    def test_remove_field_from_concepts_and_form(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="remove_field",
                target_field="Caste",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        assert not any(c["name"] == "Caste" for c in concepts)

        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        assert not any(e["name"] == "Caste" for e in elements)

    def test_remove_field_cleans_orphan_answers(self, bundle_path, bundle_id):
        """Removing a Coded field should remove its NA answer concepts if orphaned."""
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="remove_field",
                target_field="Caste",
            )
            result = apply_edit(bundle_id, cmd)

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        # SC, ST, OBC should be removed since no other concept references them
        names = [c["name"] for c in concepts]
        assert "SC" not in names
        assert "ST" not in names
        assert "OBC" not in names

    def test_remove_nonexistent_field(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="remove_field",
                target_field="Nonexistent",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False
        assert "not found" in result["error"]


# ---------------------------------------------------------------------------
# Apply Edit Tests — Make Mandatory / Optional
# ---------------------------------------------------------------------------

class TestApplyMandatory:
    """Tests for making fields mandatory or optional."""

    def test_make_mandatory(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="make_mandatory",
                target_field="Phone Number",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        phone = next(e for e in elements if e["name"] == "Phone Number")
        assert phone["mandatory"] is True

    def test_make_optional(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="make_optional",
                target_field="Weight",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        weight = next(e for e in elements if e["name"] == "Weight")
        assert weight["mandatory"] is False

    def test_mandatory_field_not_found(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="make_mandatory",
                target_field="Nonexistent",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False


# ---------------------------------------------------------------------------
# Apply Edit Tests — Change Type
# ---------------------------------------------------------------------------

class TestApplyChangeType:
    """Tests for changing field data types."""

    def test_change_type_text_to_numeric(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="change_type",
                target_field="Age",
                params={"new_type": "Numeric"},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        age = next(c for c in concepts if c["name"] == "Age")
        assert age["dataType"] == "Numeric"

        form = json.loads((bundle_path / "forms" / "Registration.json").read_text())
        elements = form["formElementGroups"][0]["formElements"]
        age_el = next(e for e in elements if e["name"] == "Age")
        assert age_el["concept"]["dataType"] == "Numeric"


# ---------------------------------------------------------------------------
# Apply Edit Tests — Add / Remove Options
# ---------------------------------------------------------------------------

class TestApplyOptions:
    """Tests for adding and removing options."""

    def test_add_option_to_coded(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="add_option",
                target_field="Gender",
                params={"options": ["Other"]},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        gender = next(c for c in concepts if c["name"] == "Gender")
        answer_names = [a["name"] for a in gender["answers"]]
        assert "Other" in answer_names
        assert len(gender["answers"]) == 3

    def test_add_option_to_non_coded_fails(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="add_option",
                target_field="Weight",
                params={"options": ["Heavy"]},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False
        assert "not Coded" in result["error"]

    def test_remove_option(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="remove_option",
                target_field="Caste",
                params={"options": ["OBC"]},
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is True

        concepts = json.loads((bundle_path / "concepts.json").read_text())
        caste = next(c for c in concepts if c["name"] == "Caste")
        answer_names = [a["name"] for a in caste["answers"]]
        assert "OBC" not in answer_names
        assert len(caste["answers"]) == 2


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Tests for error handling and edge cases."""

    def test_bundle_not_found(self):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = "/tmp/nonexistent_test_dir"
            cmd = BundleEditCommand(
                action="rename_field",
                target_field="Weight",
                params={"new_name": "Body Weight"},
            )
            result = apply_edit("no-such-bundle", cmd)

        assert result["success"] is False
        assert "not found" in result["error"]

    def test_unknown_action(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            cmd = BundleEditCommand(
                action="unknown_action",
                target_field="Weight",
            )
            result = apply_edit(bundle_id, cmd)

        assert result["success"] is False
        assert "Unknown action" in result["error"]

    def test_command_describe(self):
        cmd = BundleEditCommand(
            action="rename_field",
            target_field="Weight",
            target_form="Registration",
            params={"new_name": "Body Weight"},
        )
        desc = cmd.describe()
        assert "Weight" in desc
        assert "Body Weight" in desc
        assert "Registration" in desc


# ---------------------------------------------------------------------------
# Integration — edit_bundle_nl
# ---------------------------------------------------------------------------

class TestEditBundleNL:
    """Integration tests for the full NL edit pipeline."""

    @pytest.mark.asyncio
    async def test_nl_rename_end_to_end(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            result = await edit_bundle_nl(
                bundle_id, "rename field 'Weight' to 'Body Weight'"
            )

        assert result["success"] is True
        assert result["bundle_id"] == bundle_id
        assert len(result["commands"]) == 1
        assert result["commands"][0]["action"] == "rename_field"
        assert len(result["changes"]) > 0
        assert len(result["errors"]) == 0

    @pytest.mark.asyncio
    async def test_nl_bundle_not_found(self):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = "/tmp/nonexistent_test_dir"
            result = await edit_bundle_nl("bad-id", "rename 'X' to 'Y'")

        assert result["success"] is False
        assert "not found" in result["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_nl_empty_instruction(self, bundle_path, bundle_id):
        with patch("app.services.bundle_editor.settings") as mock_settings:
            mock_settings.BUNDLE_OUTPUT_DIR = str(bundle_path.parent)
            result = await edit_bundle_nl(bundle_id, "")

        assert result["success"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_parse_falls_back_to_llm(self):
        """When deterministic parsing fails, LLM is called."""
        mock_response = json.dumps([{
            "action": "rename_field",
            "target_field": "Weight",
            "target_form": None,
            "params": {"new_name": "Body Weight"},
        }])

        with patch("app.services.claude_client.claude_client") as mock_client:
            mock_client.complete = AsyncMock(return_value=mock_response)
            commands = await parse_edit_command(
                "please change the name of the weight concept to body weight"
            )

        assert len(commands) == 1
        assert commands[0].action == "rename_field"
        mock_client.complete.assert_called_once()
