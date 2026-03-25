"""Tests for Avni rule validator.

Tests:
- Syntax validation (balanced brackets, quotes)
- Security checks (eval, require, fetch blocked)
- Pattern consistency (ViewFilter needs FormElementStatusBuilder)
- Common mistake detection
- UUID validation
"""

import pytest

from app.services.rule_validator import validate_rule_js, _check_balanced, RuleValidationIssue


# ── Valid Rules ──────────────────────────────────────────────────────────────

VALID_VIEW_FILTER = """
'use strict';
({params, imports}) => {
    const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({
        programEnrolment: params.entity,
        formElement: params.formElement
    });
    statusBuilder.show().when.valueInEntireEnrolment("Gender").is.containsAnswerConceptName("Female");
    return statusBuilder.build();
};
"""

VALID_VISIT_SCHEDULE = """
'use strict';
({params, imports}) => {
    const scheduleBuilder = new imports.rulesConfig.VisitScheduleBuilder({
        programEnrolment: params.entity,
    });
    const scheduledVisit = scheduleBuilder.add({
        name: "ANC Visit",
        encounterType: "ANC Visit",
        earliestDate: imports.moment(params.entity.enrolmentDateTime).add(1, 'months').toDate(),
        maxDate: imports.moment(params.entity.enrolmentDateTime).add(2, 'months').toDate(),
    });
    return scheduleBuilder.getSchedule();
};
"""

VALID_DECISION = """
'use strict';
({params, imports}) => {
    const decisions = [];
    const weight = params.entity.getObservationReadableValue("Weight");
    if (weight < 40) {
        decisions.push({ name: "Risk", value: ["Underweight"] });
    }
    return { enrolmentDecisions: decisions, encounterDecisions: [], registrationDecisions: [] };
};
"""

VALID_VALIDATION = """
'use strict';
({params, imports}) => {
    const age = params.entity.getObservationReadableValue("Age");
    if (age < 0 || age > 150) {
        return imports.common.createValidationError("Age must be between 0 and 150");
    }
    return imports.common.createValidationResultSuccess();
};
"""


class TestValidRules:
    def test_valid_view_filter_rule_passes(self):
        result = validate_rule_js(VALID_VIEW_FILTER, "ViewFilter")
        assert result["valid"] is True
        assert result["error_count"] == 0

    def test_valid_visit_schedule_rule_passes(self):
        result = validate_rule_js(VALID_VISIT_SCHEDULE, "VisitSchedule")
        assert result["valid"] is True
        assert result["error_count"] == 0

    def test_valid_decision_rule_passes(self):
        result = validate_rule_js(VALID_DECISION, "Decision")
        assert result["valid"] is True

    def test_valid_validation_rule_passes(self):
        result = validate_rule_js(VALID_VALIDATION, "Validation")
        assert result["valid"] is True


# ── Security Checks ──────────────────────────────────────────────────────────

class TestSecurityChecks:
    def test_eval_detected_as_security_issue(self):
        code = "const x = eval('alert(1)');"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("eval()" in i["message"] for i in result["issues"])

    def test_require_detected_as_security_issue(self):
        code = "const fs = require('fs');"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("require()" in i["message"] for i in result["issues"])

    def test_fetch_detected_as_security_issue(self):
        code = "const data = fetch('http://evil.com');"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("fetch()" in i["message"] for i in result["issues"])

    def test_function_constructor_blocked(self):
        code = "const fn = new Function('return 1');"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("Function() constructor" in i["message"] for i in result["issues"])

    def test_xmlhttprequest_blocked(self):
        code = "const xhr = new XMLHttpRequest();"
        result = validate_rule_js(code)
        assert result["valid"] is False

    def test_process_env_blocked(self):
        code = "const secret = process.env.SECRET;"
        result = validate_rule_js(code)
        assert result["valid"] is False

    def test_fs_module_blocked(self):
        code = "fs.readFileSync('/etc/passwd');"
        result = validate_rule_js(code)
        assert result["valid"] is False

    def test_child_process_blocked(self):
        code = "child_process.exec('rm -rf /');"
        result = validate_rule_js(code)
        assert result["valid"] is False

    def test_import_statement_blocked(self):
        code = "import fs from 'fs';"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("imports are not supported" in i["message"] for i in result["issues"])


# ── Syntax Checks ────────────────────────────────────────────────────────────

class TestSyntaxChecks:
    def test_unbalanced_brackets_detected(self):
        code = "function test() { if (true) { return 1; }"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("Unclosed" in i["message"] or "Unmatched" in i["message"] for i in result["issues"])

    def test_unbalanced_parentheses_detected(self):
        code = "function test(a, b { return a + b; }"
        result = validate_rule_js(code)
        assert result["valid"] is False

    def test_extra_closing_brace(self):
        code = "function test() { return 1; }}"
        result = validate_rule_js(code)
        assert result["valid"] is False
        assert any("Unmatched" in i["message"] for i in result["issues"])

    def test_balanced_code_passes(self):
        code = "function test() { if (true) { return [1, 2]; } }"
        result = validate_rule_js(code)
        balanced_errors = [
            i for i in result["issues"]
            if "Unclosed" in i["message"] or "Unmatched" in i["message"]
        ]
        assert len(balanced_errors) == 0

    def test_strings_dont_affect_balance(self):
        code = "const s = 'text with { brackets }'; function test() { return s; }"
        result = validate_rule_js(code)
        balanced_errors = [
            i for i in result["issues"]
            if "Unclosed" in i["message"] or "Unmatched" in i["message"]
        ]
        assert len(balanced_errors) == 0

    def test_comments_dont_affect_balance(self):
        code = """
        // this has an open brace {
        function test() {
            /* and another { */
            return 1;
        }
        """
        result = validate_rule_js(code)
        balanced_errors = [
            i for i in result["issues"]
            if "Unclosed" in i["message"] or "Unmatched" in i["message"]
        ]
        assert len(balanced_errors) == 0


# ── Rule Type Pattern Checks ────────────────────────────────────────────────

class TestRuleTypePatterns:
    def test_missing_formElementStatusBuilder_for_viewfilter(self):
        code = """
        ({params, imports}) => {
            return { visibility: true, value: null };
        };
        """
        result = validate_rule_js(code, "ViewFilter")
        warnings = [i for i in result["issues"] if "FormElementStatusBuilder" in i["message"]]
        assert len(warnings) >= 1

    def test_missing_visitScheduleBuilder_for_visitschedule(self):
        code = """
        ({params, imports}) => {
            return [];
        };
        """
        result = validate_rule_js(code, "VisitSchedule")
        warnings = [i for i in result["issues"] if "VisitScheduleBuilder" in i["message"]]
        assert len(warnings) >= 1

    def test_missing_build_for_viewfilter(self):
        code = """
        ({params, imports}) => {
            const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({});
            return statusBuilder;
        };
        """
        result = validate_rule_js(code, "ViewFilter")
        warnings = [i for i in result["issues"] if ".build()" in i["message"]]
        assert len(warnings) >= 1

    def test_no_rule_type_skips_type_checks(self):
        code = """
        ({params, imports}) => {
            return {};
        };
        """
        result = validate_rule_js(code, None)
        # Should not have rule-type-specific warnings
        type_warnings = [
            i for i in result["issues"]
            if "ViewFilter" in i["message"] or "VisitSchedule" in i["message"]
        ]
        assert len(type_warnings) == 0


# ── Common Mistakes ──────────────────────────────────────────────────────────

class TestCommonMistakes:
    def test_getObservationValue_vs_readable_warning(self):
        code = """
        ({params, imports}) => {
            const val = params.entity.getObservationValue("Gender");
            return {};
        };
        """
        result = validate_rule_js(code)
        warnings = [i for i in result["issues"] if "getObservationValue" in i["message"]]
        assert len(warnings) >= 1

    def test_string_yes_no_comparison_warning(self):
        code = """
        ({params, imports}) => {
            if (gender === "Yes") { return true; }
            return false;
        };
        """
        result = validate_rule_js(code)
        warnings = [i for i in result["issues"] if "'Yes'" in i["message"] or "Yes" in i["message"]]
        assert len(warnings) >= 1

    def test_new_date_warning(self):
        code = """
        ({params, imports}) => {
            const now = new Date();
            return {};
        };
        """
        result = validate_rule_js(code)
        warnings = [i for i in result["issues"] if "moment" in i["message"].lower() or "Date" in i["message"]]
        assert len(warnings) >= 1

    def test_console_log_warning(self):
        code = """
        ({params, imports}) => {
            console.log("debug");
            return {};
        };
        """
        result = validate_rule_js(code)
        assert any("console" in i["message"] for i in result["issues"])


# ── UUID Checks ──────────────────────────────────────────────────────────────

class TestUUIDChecks:
    def test_valid_uuid_references_reported(self):
        code = """
        const conceptUUID = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
        """
        result = validate_rule_js(code)
        info_issues = [i for i in result["issues"] if i["severity"] == "info"]
        assert any("UUID" in i["message"] for i in info_issues)

    def test_no_uuid_no_info(self):
        code = """
        ({params}) => { return {}; };
        """
        result = validate_rule_js(code)
        uuid_info = [i for i in result["issues"] if i["severity"] == "info" and "UUID" in i["message"]]
        assert len(uuid_info) == 0


# ── Edge Cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_rule_handled(self):
        result = validate_rule_js("")
        assert isinstance(result, dict)
        assert "valid" in result

    def test_comment_only_rule(self):
        code = "// This is just a comment"
        result = validate_rule_js(code)
        assert isinstance(result, dict)

    def test_rule_with_arrow_functions(self):
        code = """
        const fn = (params) => {
            const vals = [1, 2, 3].map(x => x * 2);
            return { decisions: vals };
        };
        """
        result = validate_rule_js(code)
        balanced_errors = [
            i for i in result["issues"]
            if "Unclosed" in i["message"] or "Unmatched" in i["message"]
        ]
        assert len(balanced_errors) == 0

    def test_rule_with_template_literals(self):
        code = """
        const fn = (params) => {
            const msg = `Hello ${params.name}`;
            return { message: msg };
        };
        """
        result = validate_rule_js(code)
        balanced_errors = [
            i for i in result["issues"]
            if "Unclosed" in i["message"] or "Unmatched" in i["message"]
        ]
        assert len(balanced_errors) == 0

    def test_complex_nested_rule(self):
        code = """
        ({params, imports}) => {
            const statusBuilder = new imports.rulesConfig.FormElementStatusBuilder({
                programEnrolment: params.entity,
                formElement: params.formElement
            });
            if (params.entity.getObservationReadableValue("Age") > 18) {
                statusBuilder.show().when.valueInEntireEnrolment("Married").is.containsAnswerConceptName("Yes");
            }
            return statusBuilder.build();
        };
        """
        result = validate_rule_js(code, "ViewFilter")
        assert result["valid"] is True

    def test_result_format(self):
        result = validate_rule_js("const x = 1;")
        assert "valid" in result
        assert "error_count" in result
        assert "warning_count" in result
        assert "issues" in result
        assert isinstance(result["issues"], list)

    def test_issue_line_numbers_present_for_security(self):
        code = "line1\neval('bad')\nline3"
        result = validate_rule_js(code)
        eval_issues = [i for i in result["issues"] if "eval" in i["message"]]
        assert len(eval_issues) >= 1
        assert eval_issues[0].get("line") == 2

    def test_no_export_no_function_no_crash(self):
        # Code with no function definition or export should not crash
        code = """
        // This is a comment block that is long enough
        // to trigger the function export check
        const x = 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 + 10;
        """
        result = validate_rule_js(code)
        # Should still return a valid result structure
        assert "valid" in result
        assert "issues" in result

    def test_avni_imports_warning_for_long_rule(self):
        code = """
        function myRule(params) {
            const x = 1;
            const y = 2;
            const z = x + y;
            return { value: z };
        }
        module.exports = myRule;
        """
        result = validate_rule_js(code)
        import_warnings = [i for i in result["issues"] if "imports.rulesConfig" in i["message"]]
        # Only flagged for code > 100 chars
        if len(code) > 100:
            assert len(import_warnings) >= 1
