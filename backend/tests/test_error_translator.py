"""Tests for error translation service.

Tests all 14 Avni error patterns:
1. missing_concept
2. duplicate_concept
3. datatype_mismatch
4. missing_answer
5. missing_form
6. missing_subject_type
7. missing_program
8. missing_encounter_type
9. permission_error
10. auth_error
11. import_header
12. row_error
13. connection_error
14. server_error
"""

import pytest

from app.services.error_translator import translate_avni_error, translate_multiple


class TestMissingConcept:
    def test_missing_concept_detected(self):
        result = translate_avni_error("Concept with name 'Weight' not found")
        assert result["category"] == "missing_concept"
        assert result["auto_fixable"] is True
        assert "Weight" in result["suggestion"]

    def test_missing_concept_fix_action(self):
        result = translate_avni_error("Concept with name 'BP Systolic' not found")
        assert result["fix_action"] is not None
        assert result["fix_action"]["action"] == "bundle_upload"
        assert result["fix_action"]["strategy"] == "two_pass"

    def test_missing_concept_case_insensitive(self):
        result = translate_avni_error("concept with name 'Height' not found")
        assert result["category"] == "missing_concept"


class TestDuplicateConcept:
    def test_duplicate_concept_detected(self):
        result = translate_avni_error("Duplicate concept name 'Weight'")
        assert result["category"] == "duplicate_concept"
        assert result["auto_fixable"] is False

    def test_duplicate_concept_with_different_casing(self):
        result = translate_avni_error("duplicate Concept Name 'Gender'")
        assert result["category"] == "duplicate_concept"


class TestDatatypeMismatch:
    def test_datatype_mismatch_detected(self):
        result = translate_avni_error("FormElement dataType mismatch for concept")
        assert result["category"] == "datatype_mismatch"
        assert result["auto_fixable"] is False

    def test_datatype_mismatch_with_entity(self):
        result = translate_avni_error("data type mismatch for 'Weight'")
        assert result["category"] == "datatype_mismatch"


class TestMissingAnswer:
    def test_missing_answer_detected(self):
        result = translate_avni_error("ConceptAnswer not found for concept 'Status'")
        assert result["category"] == "missing_answer"
        assert result["auto_fixable"] is True

    def test_missing_answer_fix_action(self):
        result = translate_avni_error("answer concept 'Active' not found")
        assert result["fix_action"] is not None
        assert result["fix_action"]["action"] == "bundle_validate"


class TestMissingForm:
    def test_missing_form_detected(self):
        result = translate_avni_error("form 'Registration' does not exist")
        assert result["category"] == "missing_form"
        assert result["auto_fixable"] is False

    def test_missing_form_uuid(self):
        result = translate_avni_error("formMapping form UUID not found")
        assert result["category"] == "missing_form"


class TestMissingSubjectType:
    def test_missing_subject_type_detected(self):
        result = translate_avni_error("subjectType 'Individual' not found")
        assert result["category"] == "missing_subject_type"
        assert result["auto_fixable"] is True

    def test_missing_subject_type_fix_action(self):
        result = translate_avni_error("subjectType 'Household' not found")
        assert result["fix_action"] is not None
        assert result["fix_action"]["action"] == "mcp_call"
        assert result["fix_action"]["tool_name"] == "create_subject_type"
        assert result["fix_action"]["arguments"]["name"] == "Household"


class TestMissingProgram:
    def test_missing_program_detected(self):
        result = translate_avni_error("program 'Maternal Health' not found")
        assert result["category"] == "missing_program"
        assert result["auto_fixable"] is True

    def test_missing_program_fix_action(self):
        result = translate_avni_error("program 'TB' not found")
        assert result["fix_action"]["tool_name"] == "create_program"
        assert result["fix_action"]["arguments"]["name"] == "TB"


class TestMissingEncounterType:
    def test_missing_encounter_type_detected(self):
        result = translate_avni_error("encounterType 'ANC Visit' not found")
        assert result["category"] == "missing_encounter_type"
        assert result["auto_fixable"] is True

    def test_missing_encounter_type_fix_action(self):
        result = translate_avni_error("encounterType 'PNC Visit' not found")
        assert result["fix_action"]["tool_name"] == "create_encounter_type"
        assert result["fix_action"]["arguments"]["name"] == "PNC Visit"


class TestPermissionError:
    def test_permission_error_detected(self):
        result = translate_avni_error("UploadMetadataAndData permission required")
        assert result["category"] == "permission_error"
        assert result["auto_fixable"] is False

    def test_403_detected(self):
        result = translate_avni_error("403 Forbidden")
        assert result["category"] == "permission_error"

    def test_insufficient_permission(self):
        result = translate_avni_error("insufficient permission to upload")
        assert result["category"] == "permission_error"


class TestAuthError:
    def test_auth_error_detected(self):
        result = translate_avni_error("Invalid AUTH-TOKEN")
        assert result["category"] == "auth_error"
        assert result["auto_fixable"] is False

    def test_expired_token(self):
        result = translate_avni_error("expired token, please re-authenticate")
        assert result["category"] == "auth_error"

    def test_401_detected(self):
        result = translate_avni_error("401 Unauthorized")
        assert result["category"] == "auth_error"


class TestImportHeader:
    def test_import_header_detected(self):
        result = translate_avni_error("ImportSheetHeader 'InvalidCol' not recognized")
        assert result["category"] == "import_header"
        assert result["auto_fixable"] is False


class TestRowError:
    def test_row_error_detected(self):
        result = translate_avni_error("Error processing row 42 in import")
        assert result["category"] == "row_error"


class TestConnectionError:
    def test_connection_refused(self):
        result = translate_avni_error("connection refused to server")
        assert result["category"] == "connection_error"
        assert result["auto_fixable"] is False

    def test_timeout(self):
        result = translate_avni_error("Request timed out after 30s")
        assert result["category"] == "connection_error"

    def test_econnrefused(self):
        result = translate_avni_error("ECONNREFUSED 127.0.0.1:3000")
        assert result["category"] == "connection_error"


class TestServerError:
    def test_500_detected(self):
        result = translate_avni_error("500 Internal Server Error")
        assert result["category"] == "server_error"
        assert result["auto_fixable"] is False

    def test_internal_server_error(self):
        result = translate_avni_error("internal server error occurred")
        assert result["category"] == "server_error"


class TestGenericAndEdgeCases:
    def test_unrecognized_error_returns_unknown(self):
        result = translate_avni_error("Something completely unrecognized happened xyz123")
        assert result["category"] == "unknown"
        assert result["auto_fixable"] is False
        assert result["fix_action"] is None

    def test_empty_error_message(self):
        result = translate_avni_error("")
        assert result["category"] == "unknown"
        assert result["original"] == ""

    def test_very_long_error_message(self):
        long_msg = "x" * 10000
        result = translate_avni_error(long_msg)
        assert result["category"] == "unknown"
        # Suggestion should be truncated
        assert len(result["suggestion"]) < len(long_msg)

    def test_result_format(self):
        result = translate_avni_error("Concept with name 'X' not found")
        assert "original" in result
        assert "category" in result
        assert "suggestion" in result
        assert "auto_fixable" in result
        assert "fix_action" in result

    def test_original_preserved(self):
        msg = "Concept with name 'Weight' not found in org"
        result = translate_avni_error(msg)
        assert result["original"] == msg

    def test_pattern_with_quoted_entity_name(self):
        result = translate_avni_error("Concept with name 'Some Complex Name (v2)' not found")
        assert result["category"] == "missing_concept"
        assert "Some Complex Name (v2)" in result["suggestion"]

    def test_translate_multiple(self):
        errors = [
            "Concept with name 'Weight' not found",
            "500 Internal Server Error",
            "Something unknown",
        ]
        results = translate_multiple(errors)
        assert len(results) == 3
        assert results[0]["category"] == "missing_concept"
        assert results[1]["category"] == "server_error"
        assert results[2]["category"] == "unknown"

    def test_translate_multiple_empty_list(self):
        results = translate_multiple([])
        assert results == []

    def test_first_matching_pattern_wins(self):
        # "403" matches permission_error before server_error
        result = translate_avni_error("403 error occurred")
        assert result["category"] == "permission_error"

    def test_auto_fixable_flag_for_non_fixable(self):
        result = translate_avni_error("500 Internal Server Error")
        assert result["auto_fixable"] is False
        assert result["fix_action"] is None
