"""Tests for bundle validation engine.

Tests each of the 7 validation checks:
1. Duplicate concepts (case-insensitive)
2. Concept UUID cross-references in forms
3. Form mapping references
4. Cancellation forms for scheduled encounters
5. Answer UUID consistency
6. Duplicate privileges
7. Operational references
"""

import json
import os
import time
import zipfile
from pathlib import Path

import pytest

from app.services.bundle_validator import BundleValidator, ValidationIssue, validate_bundle


class TestValidationIssue:
    """Tests for the ValidationIssue data class."""

    def test_to_dict_all_fields(self):
        issue = ValidationIssue("error", "test_cat", "test msg", "file.json", "fix it")
        d = issue.to_dict()
        assert d == {
            "severity": "error",
            "category": "test_cat",
            "message": "test msg",
            "file": "file.json",
            "fix_hint": "fix it",
        }

    def test_to_dict_empty_optional_fields(self):
        issue = ValidationIssue("warning", "cat", "msg")
        d = issue.to_dict()
        assert d["file"] == ""
        assert d["fix_hint"] == ""


class TestBundleValidatorValidBundle:
    """Tests for a valid bundle that should pass all checks."""

    def test_valid_bundle_passes_all_checks(self, bundle_dir):
        result = validate_bundle(bundle_dir)
        assert result["valid"] is True
        assert result["error_count"] == 0

    def test_valid_bundle_result_format(self, bundle_dir):
        result = validate_bundle(bundle_dir)
        assert "valid" in result
        assert "error_count" in result
        assert "warning_count" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_valid_concept_references_pass(self, bundle_dir):
        result = validate_bundle(bundle_dir)
        missing_concept_issues = [
            i for i in result["issues"] if i["category"] == "missing_concept"
        ]
        assert len(missing_concept_issues) == 0

    def test_valid_form_mappings_pass(self, bundle_dir):
        result = validate_bundle(bundle_dir)
        orphaned = [i for i in result["issues"] if i["category"] == "orphaned_mapping"]
        assert len(orphaned) == 0

    def test_valid_answer_uuids_pass(self, bundle_dir):
        result = validate_bundle(bundle_dir)
        answer_issues = [
            i for i in result["issues"] if i["category"] == "answer_uuid_mismatch"
        ]
        assert len(answer_issues) == 0


class TestDuplicateConcepts:
    """Tests for check 1: duplicate concept detection."""

    def test_duplicate_concept_names_detected(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "u2", "name": "Weight", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) == 1
        assert "Weight" in dup_issues[0]["message"]

    def test_duplicate_concept_names_case_insensitive(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "u2", "name": "weight", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) >= 1

    def test_duplicate_with_leading_trailing_spaces(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "u2", "name": "  Weight  ", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) >= 1

    def test_unique_concepts_no_duplicates(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "u2", "name": "Height", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) == 0

    def test_unicode_concept_names(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Poids", "dataType": "Numeric"},
            {"uuid": "u2", "name": "poids", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) >= 1

    def test_special_characters_in_names(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "BP (Systolic)", "dataType": "Numeric"},
            {"uuid": "u2", "name": "BP (Diastolic)", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert len(dup_issues) == 0

    def test_duplicate_severity_is_error(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
            {"uuid": "u2", "name": "Weight", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        assert all(i["severity"] == "error" for i in dup_issues)


class TestConceptUUIDReferences:
    """Tests for check 2: concept UUID cross-references in forms."""

    def test_missing_concept_uuid_in_form(self, tmp_path):
        concepts = [{"uuid": "u1", "name": "Weight", "dataType": "Numeric"}]
        form = {
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": [{
                "uuid": "feg1", "name": "G1",
                "formElements": [
                    {"uuid": "fe1", "concept": {"uuid": "u-missing", "name": "Missing"}}
                ]
            }]
        }
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps(form))

        result = validate_bundle(str(tmp_path))
        missing = [i for i in result["issues"] if i["category"] == "missing_concept"]
        assert len(missing) == 1
        assert "u-missing" in missing[0]["message"]

    def test_valid_concept_references_in_form(self, tmp_path):
        concepts = [{"uuid": "u1", "name": "Weight", "dataType": "Numeric"}]
        form = {
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": [{
                "uuid": "feg1", "name": "G1",
                "formElements": [
                    {"uuid": "fe1", "concept": {"uuid": "u1", "name": "Weight"}}
                ]
            }]
        }
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps(form))

        result = validate_bundle(str(tmp_path))
        missing = [i for i in result["issues"] if i["category"] == "missing_concept"]
        assert len(missing) == 0


class TestFormMappingReferences:
    """Tests for check 3: form mapping references."""

    def test_orphaned_form_mapping_detected(self, tmp_path):
        mappings = [
            {"uuid": "fm1", "formUUID": "form-nonexistent", "formName": "Ghost",
             "subjectTypeUUID": "", "programUUID": "", "encounterTypeUUID": ""}
        ]
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))
        result = validate_bundle(str(tmp_path))
        orphaned = [i for i in result["issues"] if i["category"] == "orphaned_mapping"]
        assert len(orphaned) == 1

    def test_missing_subject_type_in_mapping(self, tmp_path):
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps({
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": []
        }))
        mappings = [
            {"uuid": "fm1", "formUUID": "f1", "subjectTypeUUID": "st-missing",
             "programUUID": "", "encounterTypeUUID": ""}
        ]
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))
        result = validate_bundle(str(tmp_path))
        st_issues = [i for i in result["issues"] if i["category"] == "missing_subject_type"]
        assert len(st_issues) == 1
        assert st_issues[0]["severity"] == "error"

    def test_missing_program_in_mapping(self, tmp_path):
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps({
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": []
        }))
        mappings = [
            {"uuid": "fm1", "formUUID": "f1", "subjectTypeUUID": "",
             "programUUID": "pg-missing", "encounterTypeUUID": ""}
        ]
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))
        result = validate_bundle(str(tmp_path))
        pg_issues = [i for i in result["issues"] if i["category"] == "missing_program"]
        assert len(pg_issues) == 1

    def test_missing_encounter_type_in_mapping(self, tmp_path):
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps({
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": []
        }))
        mappings = [
            {"uuid": "fm1", "formUUID": "f1", "subjectTypeUUID": "",
             "programUUID": "", "encounterTypeUUID": "et-missing"}
        ]
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))
        result = validate_bundle(str(tmp_path))
        et_issues = [i for i in result["issues"] if i["category"] == "missing_encounter_type"]
        assert len(et_issues) == 1


class TestCancellationForms:
    """Tests for check 4: cancellation forms for scheduled encounters."""

    def test_missing_cancellation_form_detected(self, tmp_path):
        encounter_types = [{"uuid": "et-1", "name": "ANC Visit"}]
        mappings = [
            {"uuid": "fm1", "formUUID": "f1", "formType": "ProgramEncounter",
             "subjectTypeUUID": "", "programUUID": "", "encounterTypeUUID": "et-1"},
        ]
        (tmp_path / "encounterTypes.json").write_text(json.dumps(encounter_types))
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))

        result = validate_bundle(str(tmp_path))
        cancel_issues = [i for i in result["issues"] if i["category"] == "missing_cancellation"]
        assert len(cancel_issues) == 1
        assert "ANC Visit" in cancel_issues[0]["message"]
        assert cancel_issues[0]["severity"] == "warning"

    def test_cancellation_form_present_passes(self, tmp_path):
        encounter_types = [{"uuid": "et-1", "name": "ANC Visit"}]
        mappings = [
            {"uuid": "fm1", "formUUID": "f1", "formType": "ProgramEncounter",
             "subjectTypeUUID": "", "programUUID": "", "encounterTypeUUID": "et-1"},
            {"uuid": "fm2", "formUUID": "f2", "formType": "ProgramEncounterCancellation",
             "subjectTypeUUID": "", "programUUID": "", "encounterTypeUUID": "et-1"},
        ]
        (tmp_path / "encounterTypes.json").write_text(json.dumps(encounter_types))
        (tmp_path / "formMappings.json").write_text(json.dumps(mappings))

        result = validate_bundle(str(tmp_path))
        cancel_issues = [i for i in result["issues"] if i["category"] == "missing_cancellation"]
        assert len(cancel_issues) == 0


class TestAnswerUUIDConsistency:
    """Tests for check 5: answer UUID consistency."""

    def test_answer_uuid_mismatch_detected(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Status", "dataType": "Coded",
             "answers": [{"uuid": "ans-missing", "name": "Active"}]},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        answer_issues = [i for i in result["issues"] if i["category"] == "missing_answer"]
        assert len(answer_issues) == 1
        assert answer_issues[0]["severity"] == "warning"

    def test_valid_answer_uuids_pass(self, tmp_path):
        concepts = [
            {"uuid": "ans-1", "name": "Active", "dataType": "NA"},
            {"uuid": "u1", "name": "Status", "dataType": "Coded",
             "answers": [{"uuid": "ans-1", "name": "Active"}]},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        answer_issues = [i for i in result["issues"]
                         if i["category"] in ("answer_uuid_mismatch", "missing_answer")]
        assert len(answer_issues) == 0

    def test_non_coded_concepts_skip_answer_check(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "Weight", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        answer_issues = [i for i in result["issues"]
                         if i["category"] in ("answer_uuid_mismatch", "missing_answer")]
        assert len(answer_issues) == 0


class TestDuplicatePrivileges:
    """Tests for check 6: duplicate privileges."""

    def test_duplicate_privileges_detected(self, tmp_path):
        privs = [
            {"groupUUID": "g1", "privilegeType": "EditSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},
            {"groupUUID": "g1", "privilegeType": "EditSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},
        ]
        (tmp_path / "groupPrivilege.json").write_text(json.dumps(privs))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_privilege"]
        assert len(dup_issues) == 1
        assert dup_issues[0]["severity"] == "warning"

    def test_unique_privileges_pass(self, tmp_path):
        privs = [
            {"groupUUID": "g1", "privilegeType": "EditSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},
            {"groupUUID": "g1", "privilegeType": "ViewSubject", "subjectTypeUUID": "st-1",
             "programUUID": "", "encounterTypeUUID": ""},
        ]
        (tmp_path / "groupPrivilege.json").write_text(json.dumps(privs))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_privilege"]
        assert len(dup_issues) == 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_bundle_handled_gracefully(self, tmp_path):
        """An empty directory should report missing file errors but not crash."""
        result = validate_bundle(str(tmp_path))
        # Empty bundle is NOT valid — required files are missing
        assert result["valid"] is False
        assert result["error_count"] > 0
        missing_issues = [i for i in result["issues"] if i["category"] == "missing_file"]
        assert len(missing_issues) > 0

    def test_bundle_with_no_forms(self, tmp_path):
        concepts = [{"uuid": "u1", "name": "Weight", "dataType": "Numeric"}]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        # Missing forms/ directory is an error
        assert result["valid"] is False

    def test_bundle_with_no_concepts(self, tmp_path):
        forms_dir = tmp_path / "forms"
        forms_dir.mkdir()
        (forms_dir / "Reg.json").write_text(json.dumps({
            "uuid": "f1", "name": "Reg", "formType": "IndividualProfile",
            "formElementGroups": []
        }))
        result = validate_bundle(str(tmp_path))
        assert isinstance(result["issues"], list)

    def test_multiple_issues_all_reported(self, invalid_bundle_dir):
        result = validate_bundle(invalid_bundle_dir)
        assert result["valid"] is False
        categories = {i["category"] for i in result["issues"]}
        # Should detect at least duplicate concept, missing concept, orphaned mapping
        assert "duplicate_concept" in categories
        assert "missing_concept" in categories

    def test_fix_hints_provided(self, invalid_bundle_dir):
        result = validate_bundle(invalid_bundle_dir)
        error_issues = [i for i in result["issues"] if i["severity"] == "error"]
        for issue in error_issues:
            # All error issues should have a non-empty fix_hint
            assert issue["fix_hint"] != "" or issue["category"] == "parse"

    def test_severity_classification(self, invalid_bundle_dir):
        result = validate_bundle(invalid_bundle_dir)
        for issue in result["issues"]:
            assert issue["severity"] in ("error", "warning")

    @pytest.mark.slow
    def test_large_bundle_performance(self, tmp_path):
        """Validate a bundle with 200 concepts completes in reasonable time."""
        concepts = [
            {"uuid": f"u-{i}", "name": f"Concept {i}", "dataType": "Numeric"}
            for i in range(200)
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))

        start = time.time()
        result = validate_bundle(str(tmp_path))
        elapsed = time.time() - start

        # May have missing file errors (only concepts.json provided),
        # but concept validation itself should not produce issues
        concept_issues = [i for i in result["issues"]
                          if i["category"] not in ("missing_file", "invalid_json")]
        assert len(concept_issues) == 0
        assert elapsed < 5.0  # Should complete well under 5 seconds

    def test_malformed_json_reports_parse_error(self, tmp_path):
        (tmp_path / "concepts.json").write_text("{ invalid json")
        result = validate_bundle(str(tmp_path))
        parse_issues = [i for i in result["issues"] if i["category"] == "parse"]
        assert len(parse_issues) == 1
        assert parse_issues[0]["severity"] == "error"

    def test_zip_bundle(self, bundle_dir, tmp_path):
        """Test validation of a zipped bundle."""
        zip_path = str(tmp_path / "bundle.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            for root, dirs, files in os.walk(bundle_dir):
                for f in files:
                    full = os.path.join(root, f)
                    arcname = os.path.relpath(full, bundle_dir)
                    zf.write(full, arcname)
        result = validate_bundle(zip_path)
        assert result["valid"] is True

    def test_concepts_json_not_a_list(self, tmp_path):
        """Non-list concepts.json should not crash."""
        (tmp_path / "concepts.json").write_text(json.dumps({"not": "a list"}))
        result = validate_bundle(str(tmp_path))
        # Should not raise; just has no concepts to check
        assert isinstance(result, dict)

    def test_empty_concept_name_skipped(self, tmp_path):
        concepts = [
            {"uuid": "u1", "name": "", "dataType": "Numeric"},
            {"uuid": "u2", "name": "", "dataType": "Numeric"},
        ]
        (tmp_path / "concepts.json").write_text(json.dumps(concepts))
        result = validate_bundle(str(tmp_path))
        dup_issues = [i for i in result["issues"] if i["category"] == "duplicate_concept"]
        # Empty names should be skipped by the duplicate check
        assert len(dup_issues) == 0
