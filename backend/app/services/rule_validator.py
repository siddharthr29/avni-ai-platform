"""Avni Rule Validator.

Validates JavaScript rules against Avni rule engine patterns
without executing them. Catches syntax issues, security problems,
and common rule authoring mistakes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

UUID_V4_PATTERN = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)

# Forbidden patterns (security)
FORBIDDEN_PATTERNS = [
    (re.compile(r"\beval\s*\("), "eval() is forbidden — security risk"),
    (re.compile(r"\bFunction\s*\("), "Function() constructor is forbidden — security risk"),
    (re.compile(r"\brequire\s*\("), "require() is not available in Avni rule engine"),
    (re.compile(r"\bimport\s+"), "ES module imports are not supported in Avni rules"),
    (re.compile(r"\bfetch\s*\("), "fetch() is not available in Avni rule engine (offline-first)"),
    (re.compile(r"\bXMLHttpRequest\b"), "XMLHttpRequest is not available in Avni rule engine"),
    (re.compile(r"\bprocess\."), "process object is not available in Avni rule engine"),
    (re.compile(r"\bfs\."), "fs module is not available in Avni rule engine"),
    (re.compile(r"\bchild_process\b"), "child_process is not available in Avni rule engine"),
    (
        re.compile(r"\bconsole\.(log|warn|error|debug)\b"),
        "console methods may not work on all devices — use statusBuilder or return values instead",
    ),
]

# Avni rule engine globals that SHOULD be present
VALID_IMPORTS = {
    "imports.rulesConfig",
    "imports.common",
    "imports.moment",
    "imports.lodash",
    "imports._",
}

# Rule type -> expected builder/API usage
RULE_TYPE_PATTERNS: dict[str, list[tuple[re.Pattern[str], bool, str]]] = {
    "ViewFilter": [
        (
            re.compile(r"FormElementStatusBuilder|FormElementStatus"),
            True,
            "ViewFilter rules should use FormElementStatusBuilder",
        ),
        (
            re.compile(r"\.build\(\)"),
            True,
            "ViewFilter rules should call .build() to return status",
        ),
    ],
    "VisitSchedule": [
        (
            re.compile(r"VisitScheduleBuilder"),
            True,
            "VisitSchedule rules should use VisitScheduleBuilder",
        ),
        (
            re.compile(r"\.getSchedule\(\)|\.getAllSchedules\(\)"),
            True,
            "VisitSchedule rules should return schedule via getSchedule/getAllSchedules",
        ),
    ],
    "Decision": [
        (
            re.compile(r"decisions|getDecisions"),
            True,
            "Decision rules should return decisions array",
        ),
    ],
    "Validation": [
        (
            re.compile(r"createValidationError|ValidationResult|Success"),
            True,
            "Validation rules should use createValidationError or return Success/Failure",
        ),
    ],
}

# Common mistakes
COMMON_MISTAKES = [
    (
        re.compile(r"getObservationValue\s*\(\s*['\"]"),
        "warning",
        "getObservationValue returns raw values for Coded concepts (UUIDs). "
        "Use getObservationReadableValue for display names, or containsAnswerConceptName for comparisons.",
    ),
    (
        re.compile(r"===?\s*['\"]Yes['\"]|===?\s*['\"]No['\"]"),
        "warning",
        "Comparing with string 'Yes'/'No' may fail. Use concept names with "
        "containsAnswerConceptName() or getObservationReadableValue().",
    ),
    (
        re.compile(r"new\s+Date\s*\("),
        "warning",
        "Prefer imports.moment() over new Date() for consistent date handling across devices.",
    ),
    (
        re.compile(r"\.getTime\s*\(\)"),
        "warning",
        "Prefer moment .diff() or .isBefore()/.isAfter() over timestamp arithmetic.",
    ),
]


@dataclass
class RuleValidationIssue:
    severity: str  # "error" | "warning" | "info"
    message: str
    line: int | None = None

    def to_dict(self) -> dict:
        d: dict = {"severity": self.severity, "message": self.message}
        if self.line is not None:
            d["line"] = self.line
        return d


def validate_rule_js(code: str, rule_type: str | None = None) -> dict:
    """Validate a JavaScript rule against Avni patterns.

    Args:
        code: JavaScript source code.
        rule_type: Optional rule type (ViewFilter, VisitSchedule, Decision,
                   Validation, Checklist, EnrolmentSummary, Eligibility).

    Returns:
        ``{"valid": bool, "error_count": int, "warning_count": int, "issues": [...]}``
    """
    issues: list[RuleValidationIssue] = []
    lines = code.split("\n")

    # 1. Syntax: balanced delimiters
    _check_balanced(code, issues)

    # 2. Forbidden patterns (security)
    for pattern, msg in FORBIDDEN_PATTERNS:
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                issues.append(RuleValidationIssue("error", msg, i))

    # 3. Check for valid Avni imports usage
    has_avni_import = any(imp in code for imp in VALID_IMPORTS)
    if not has_avni_import and len(code) > 100:
        issues.append(
            RuleValidationIssue(
                "warning",
                "Rule doesn't reference any Avni imports (imports.rulesConfig, imports.common, "
                "imports.moment). Most Avni rules require these.",
            )
        )

    # 4. UUID format check
    uuids_found = UUID_V4_PATTERN.findall(code)
    if uuids_found:
        issues.append(
            RuleValidationIssue(
                "info",
                f"Rule references {len(uuids_found)} UUID(s). Ensure they match your concepts.json.",
            )
        )

    # 5. Rule type-specific checks
    if rule_type and rule_type in RULE_TYPE_PATTERNS:
        for pattern, required, msg in RULE_TYPE_PATTERNS[rule_type]:
            if required and not pattern.search(code):
                issues.append(RuleValidationIssue("warning", msg))

    # 6. Common mistakes
    for pattern, severity, msg in COMMON_MISTAKES:
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                issues.append(RuleValidationIssue(severity, msg, i))
                break  # Only report each mistake once

    # 7. Function export check
    has_export = bool(
        re.search(r"module\.exports|export\s+(default\s+)?function|exports\.", code)
    )
    has_function = bool(
        re.search(r"function\s+\w+|const\s+\w+\s*=\s*\(|=>\s*\{", code)
    )
    if not has_export and not has_function and len(code.strip()) > 50:
        issues.append(
            RuleValidationIssue(
                "warning",
                "No function definition or module.exports found. Avni rules must export a function.",
            )
        )

    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "issues": [i.to_dict() for i in issues],
    }


def _check_balanced(code: str, issues: list[RuleValidationIssue]) -> None:
    """Check for balanced braces, brackets, and parentheses."""
    stack: list[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    openers = set(pairs.values())
    closers = set(pairs.keys())
    in_string = False
    string_char: str | None = None
    escaped = False
    in_line_comment = False
    in_block_comment = False

    for i, ch in enumerate(code):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            continue
        if in_block_comment:
            if ch == "*" and i + 1 < len(code) and code[i + 1] == "/":
                in_block_comment = False
            continue
        if in_string:
            if ch == string_char:
                in_string = False
            continue
        if ch in ("'", '"', "`"):
            in_string = True
            string_char = ch
            continue
        if ch == "/" and i + 1 < len(code):
            if code[i + 1] == "/":
                in_line_comment = True
                continue
            if code[i + 1] == "*":
                in_block_comment = True
                continue
        if ch in openers:
            stack.append(ch)
        elif ch in closers:
            if not stack or stack[-1] != pairs[ch]:
                line_num = code[:i].count("\n") + 1
                issues.append(RuleValidationIssue("error", f"Unmatched '{ch}'", line_num))
                return
            stack.pop()

    if stack:
        issues.append(
            RuleValidationIssue("error", f"Unclosed delimiter(s): {''.join(stack)}")
        )
