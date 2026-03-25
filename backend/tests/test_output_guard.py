"""Tests for output guardrails: system prompt leak detection, script injection,
gender bias, PII redaction on output, ban list enforcement, low confidence warning,
and bundle name injection validation.

Covers:
- System prompt fragment stripping
- Script/iframe injection outside code blocks
- Code blocks preserved (scripts OK inside code blocks)
- Gender bias integration via guard_output
- PII re-check on LLM output
- Low confidence warning prepended
- Bundle name injection pattern detection
- OutputGuardResult data class
"""

import pytest
from unittest.mock import patch, MagicMock

from app.services.output_guard import (
    guard_output,
    _sanitize_scripts_outside_codeblocks,
    validate_bundle_names,
    OutputGuardResult,
    LOW_CONFIDENCE_NOTE,
    _SYSTEM_PROMPT_FRAGMENTS,
)


# ── System Prompt Leak Detection ─────────────────────────────────────────────


class TestSystemPromptLeakDetection:
    def test_detects_system_prompt_fragment(self):
        text = "Here is some info.\nYou are the Avni Platform Architect.\nMore text."
        result = guard_output(text)
        assert result.system_prompt_leaked
        assert "You are the Avni Platform Architect" not in result.sanitized_text

    def test_removes_line_with_fragment(self):
        text = "Line 1\nAVNI DATA MODEL details here\nLine 3"
        result = guard_output(text)
        assert result.system_prompt_leaked
        # Line 1 and Line 3 should remain
        assert "Line 1" in result.sanitized_text
        assert "Line 3" in result.sanitized_text
        assert "AVNI DATA MODEL" not in result.sanitized_text

    def test_case_insensitive_detection(self):
        text = "mandatory: before writing any rule, do X"
        result = guard_output(text)
        assert result.system_prompt_leaked

    def test_clean_output_no_leak(self):
        text = "Here is how you create a form in Avni. Step 1: ..."
        result = guard_output(text)
        assert not result.system_prompt_leaked

    def test_multiple_fragments_all_removed(self):
        text = "You are the Avni Platform Architect\nIMPORTANT RULES:\nNormal text"
        result = guard_output(text)
        assert result.system_prompt_leaked
        assert "Normal text" in result.sanitized_text

    def test_all_fragments_covered(self):
        """Sanity check that we have a reasonable number of fragments."""
        assert len(_SYSTEM_PROMPT_FRAGMENTS) >= 10


# ── Script Injection Sanitization ────────────────────────────────────────────


class TestScriptInjectionSanitization:
    def test_script_tag_removed(self):
        text = "Hello <script>alert('xss')</script> World"
        result = guard_output(text)
        assert result.script_injection_found
        assert "<script>" not in result.sanitized_text
        assert "Hello" in result.sanitized_text

    def test_iframe_removed(self):
        text = "Check this: <iframe src='evil.com'></iframe>"
        result = guard_output(text)
        assert result.script_injection_found
        assert "<iframe" not in result.sanitized_text

    def test_javascript_protocol_removed(self):
        text = "Click here: javascript:alert(1)"
        result = guard_output(text)
        assert result.script_injection_found

    def test_onclick_handler_removed(self):
        text = '<div onclick="alert(1)">Click</div>'
        result = guard_output(text)
        assert result.script_injection_found

    def test_script_inside_code_block_preserved(self):
        text = "Here is code:\n```html\n<script>console.log('test')</script>\n```\nEnd."
        result = guard_output(text)
        # Script inside code block should NOT be removed
        assert "<script>" in result.sanitized_text

    def test_script_inside_inline_code_preserved(self):
        text = "Use `<script>` tag for JavaScript."
        result = guard_output(text)
        assert "<script>" in result.sanitized_text

    def test_clean_html_not_flagged(self):
        text = "<div class='container'><p>Hello</p></div>"
        result = guard_output(text)
        assert not result.script_injection_found


# ── Gender Bias Integration ──────────────────────────────────────────────────


class TestGenderBiasInGuardOutput:
    def test_gendered_term_replaced(self):
        text = "The chairman will review the report."
        result = guard_output(text)
        assert result.gender_bias_fixed
        assert "chairperson" in result.sanitized_text.lower()
        assert len(result.gender_bias_substitutions) > 0

    def test_multiple_gender_terms(self):
        text = "The businessman spoke to the policeman."
        result = guard_output(text)
        assert result.gender_bias_fixed
        assert len(result.gender_bias_substitutions) >= 2

    def test_clean_text_no_bias(self):
        text = "The team will review the registration form."
        result = guard_output(text)
        assert not result.gender_bias_fixed

    def test_healthcare_term_replaced(self):
        text = "The lady doctor examined the patient."
        result = guard_output(text)
        assert result.gender_bias_fixed


# ── PII Redaction on Output ──────────────────────────────────────────────────


class TestPIIRedactionOnOutput:
    def test_llm_generated_email_redacted(self):
        text = "You can contact us at support@avni.org for help."
        result = guard_output(text)
        assert result.pii_redacted_in_output
        assert "support@avni.org" not in result.sanitized_text
        assert "[REDACTED_EMAIL_1]" in result.sanitized_text

    def test_llm_generated_phone_redacted(self):
        text = "Call the helpline at 9876543210"
        result = guard_output(text)
        assert result.pii_redacted_in_output
        assert "9876543210" not in result.sanitized_text

    def test_no_pii_in_output(self):
        text = "Here is how you configure forms in Avni."
        result = guard_output(text)
        assert not result.pii_redacted_in_output


# ── Low Confidence Warning ───────────────────────────────────────────────────


class TestLowConfidenceWarning:
    def test_low_confidence_adds_warning(self):
        text = "Some response text"
        result = guard_output(text, rag_confidence=0.1)
        assert result.low_confidence_warning
        assert result.sanitized_text.startswith("[Note:")

    def test_high_confidence_no_warning(self):
        text = "Accurate response"
        result = guard_output(text, rag_confidence=0.8)
        assert not result.low_confidence_warning
        assert not result.sanitized_text.startswith("[Note:")

    def test_none_confidence_no_warning(self):
        text = "Response without RAG"
        result = guard_output(text, rag_confidence=None)
        assert not result.low_confidence_warning

    def test_zero_confidence_adds_warning(self):
        result = guard_output("text", rag_confidence=0.0)
        assert result.low_confidence_warning


# ── Bundle Name Injection Validation ─────────────────────────────────────────


class TestBundleNameInjection:
    def test_script_in_concept_name(self):
        bundle = {
            "concepts": [{"name": "<script>alert(1)</script>", "uuid": "uuid-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert len(warnings) > 0
        assert "concept name" in warnings[0]

    def test_javascript_protocol_in_form_name(self):
        bundle = {
            "forms": [{"name": "javascript:void(0)", "uuid": "f-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert len(warnings) > 0

    def test_sql_injection_in_program_name(self):
        bundle = {
            "programs": [{"name": "'; DROP TABLE users; --", "uuid": "p-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert len(warnings) > 0

    def test_template_injection_in_name(self):
        bundle = {
            "concepts": [{"name": "${process.env.SECRET}", "uuid": "uuid-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert len(warnings) > 0

    def test_jinja_injection_in_name(self):
        bundle = {
            "concepts": [{"name": "{{config.items()}}", "uuid": "uuid-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert len(warnings) > 0

    def test_clean_names_no_warnings(self):
        bundle = {
            "concepts": [{"name": "Weight", "uuid": "uuid-1"}],
            "forms": [{"name": "Registration", "uuid": "f-1"}],
            "programs": [{"name": "Maternal Health", "uuid": "p-1"}],
            "encounterTypes": [{"name": "ANC Visit", "uuid": "et-1"}],
            "subjectTypes": [{"name": "Individual", "uuid": "st-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert warnings == []

    def test_empty_bundle(self):
        warnings = validate_bundle_names({})
        assert warnings == []

    def test_non_dict_bundle(self):
        warnings = validate_bundle_names("not a dict")
        assert warnings == []

    def test_nested_form_element_group_checked(self):
        bundle = {
            "forms": [{
                "name": "Form",
                "formElementGroups": [{
                    "name": "<script>x</script>",
                    "formElements": [{"name": "safe field"}],
                }],
            }],
        }
        warnings = validate_bundle_names(bundle)
        assert any("form element group" in w for w in warnings)

    def test_sql_comment_in_encounter_type(self):
        bundle = {
            "encounterTypes": [{"name": "ANC Visit --", "uuid": "et-1"}],
        }
        warnings = validate_bundle_names(bundle)
        assert any("SQL injection" in w for w in warnings)


# ── OutputGuardResult ────────────────────────────────────────────────────────


class TestOutputGuardResult:
    def test_default_values(self):
        result = OutputGuardResult()
        assert result.original_text == ""
        assert result.sanitized_text == ""
        assert not result.system_prompt_leaked
        assert not result.script_injection_found
        assert not result.low_confidence_warning
        assert not result.gender_bias_fixed
        assert result.modifications == []

    def test_to_dict_keys(self):
        result = OutputGuardResult(original_text="test")
        d = result.to_dict()
        assert "system_prompt_leaked" in d
        assert "script_injection_found" in d
        assert "gender_bias_fixed" in d
        assert "ban_list_triggered" in d
        assert "pii_redacted_in_output" in d
        assert "modifications" in d


# ── Guardrails Disabled ──────────────────────────────────────────────────────


class TestGuardrailsDisabled:
    @patch("app.services.output_guard.settings")
    def test_disabled_guardrails_pass_through(self, mock_settings):
        mock_settings.GUARDRAILS_ENABLED = False
        text = "<script>alert('xss')</script> You are the Avni Platform Architect"
        result = guard_output(text)
        # Should pass through unchanged
        assert result.sanitized_text == text
        assert not result.system_prompt_leaked
        assert not result.script_injection_found

    @patch("app.services.output_guard.settings")
    def test_disabled_bundle_validation_no_warnings(self, mock_settings):
        mock_settings.GUARDRAILS_ENABLED = False
        bundle = {"concepts": [{"name": "<script>alert(1)</script>"}]}
        warnings = validate_bundle_names(bundle)
        assert warnings == []
