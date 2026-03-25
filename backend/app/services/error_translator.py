"""Avni Error Translation Service.

Maps common Avni server errors to actionable fix suggestions
for both the agent loop and the user-facing chat.

Error classes from Cohort 2 notes:
- ImportSheetHeader errors (schema mismatches)
- FormElement to Concept data type mismatches
- ConceptAnswer / coded concept mismatches
- Duplicate concept names
- Missing form mappings
- Permission errors
"""

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TranslatedError:
    original: str
    category: str
    suggestion: str
    auto_fixable: bool
    fix_action: dict | None = None  # If auto_fixable, the action to take


# Pattern -> (category, suggestion_template, auto_fixable)
ERROR_PATTERNS: list[tuple[re.Pattern, str, str, bool]] = [
    # Import/upload errors
    (
        re.compile(r"(?i)Concept with name '([^']+)' not found"),
        "missing_concept",
        "Concept '{0}' doesn't exist in the org. Upload concepts.json first (two-pass upload), or add the concept to your bundle.",
        True,
    ),
    (
        re.compile(r"(?i)duplicate.*concept.*name.*'([^']*)'"),
        "duplicate_concept",
        "Concept '{0}' already exists. Either use the existing UUID or rename the new concept.",
        False,
    ),
    (
        re.compile(r"(?i)FormElement.*dataType.*mismatch|data\s*type.*mismatch.*'([^']*)'"),
        "datatype_mismatch",
        "Form element data type doesn't match the concept's data type. Check that Numeric concepts use Numeric form elements, Coded concepts use SingleSelect/MultiSelect, etc.",
        False,
    ),
    (
        re.compile(r"(?i)ConceptAnswer.*not found|answer.*concept.*'([^']*)'.*not found"),
        "missing_answer",
        "Answer concept '{0}' is referenced but not defined. Define it as an NA-type concept before the coded concept that uses it.",
        True,
    ),
    (
        re.compile(r"(?i)formMapping.*form.*UUID.*not found|form.*'([^']*)'.*does not exist"),
        "missing_form",
        "Form '{0}' is referenced in formMappings but doesn't exist. Create the form JSON file or fix the UUID reference.",
        False,
    ),
    (
        re.compile(r"(?i)subjectType.*'([^']*)'.*not found|subject.*type.*does not exist"),
        "missing_subject_type",
        "Subject type '{0}' doesn't exist. Create it via MCP (create_subject_type) or add to subjectTypes.json.",
        True,
    ),
    (
        re.compile(r"(?i)program.*'([^']*)'.*not found|program.*does not exist"),
        "missing_program",
        "Program '{0}' doesn't exist. Create it via MCP (create_program) or add to programs.json.",
        True,
    ),
    (
        re.compile(r"(?i)encounterType.*'([^']*)'.*not found|encounter.*type.*does not exist"),
        "missing_encounter_type",
        "Encounter type '{0}' doesn't exist. Create it via MCP (create_encounter_type) or add to encounterTypes.json.",
        True,
    ),
    # Permission errors
    (
        re.compile(r"(?i)UploadMetadataAndData|insufficient.*permission|403"),
        "permission_error",
        "User lacks the 'UploadMetadataAndData' privilege. Ask an org admin to grant this permission.",
        False,
    ),
    (
        re.compile(r"(?i)Invalid.*AUTH-TOKEN|401|expired.*token"),
        "auth_error",
        "Auth token is invalid or expired. Get a fresh token from Avni login.",
        False,
    ),
    # Import format errors
    (
        re.compile(r"(?i)ImportSheetHeader.*'([^']*)'|header.*not recognized.*'([^']*)'"),
        "import_header",
        "Import sheet has unrecognized header '{0}'. Check the column names match Avni's expected format.",
        False,
    ),
    (
        re.compile(r"(?i)Error processing row (\d+)|row (\d+).*error"),
        "row_error",
        "Error at row {0}. Check that all required fields are filled and data types are correct.",
        False,
    ),
    # Connection errors
    (
        re.compile(r"(?i)connection.*refused|ECONNREFUSED|timeout|timed?\s*out"),
        "connection_error",
        "Cannot connect to Avni server. Check that the server URL is correct and the server is running.",
        False,
    ),
    # Catch-all for server errors
    (
        re.compile(r"(?i)500|internal server error"),
        "server_error",
        "Avni server returned an internal error. This is likely a server-side issue. Try again or check server logs.",
        False,
    ),
]


def translate_avni_error(error_message: str) -> dict:
    """Translate an Avni error into an actionable suggestion.

    Returns:
        {
            "original": str,
            "category": str,
            "suggestion": str,
            "auto_fixable": bool,
            "fix_action": dict | None
        }
    """
    for pattern, category, suggestion_template, auto_fixable in ERROR_PATTERNS:
        match = pattern.search(error_message)
        if match:
            # Extract captured groups for template substitution
            groups = [g for g in match.groups() if g is not None]
            try:
                suggestion = suggestion_template.format(*groups) if groups else suggestion_template
            except (IndexError, KeyError):
                suggestion = suggestion_template

            fix_action = None
            if auto_fixable and category == "missing_concept":
                fix_action = {
                    "action": "bundle_upload",
                    "strategy": "two_pass",
                    "description": "Re-upload with concepts-first strategy",
                }
            elif auto_fixable and category == "missing_answer":
                fix_action = {
                    "action": "bundle_validate",
                    "description": "Run bundle validation to find all missing answer concepts",
                }
            elif auto_fixable and category in (
                "missing_subject_type",
                "missing_program",
                "missing_encounter_type",
            ):
                entity_name = groups[0] if groups else ""
                tool_map = {
                    "missing_subject_type": "create_subject_type",
                    "missing_program": "create_program",
                    "missing_encounter_type": "create_encounter_type",
                }
                fix_action = {
                    "action": "mcp_call",
                    "tool_name": tool_map[category],
                    "arguments": {"name": entity_name},
                    "description": f"Create {category.replace('missing_', '')} '{entity_name}' via MCP",
                }

            return {
                "original": error_message,
                "category": category,
                "suggestion": suggestion,
                "auto_fixable": auto_fixable,
                "fix_action": fix_action,
            }

    # No pattern matched
    return {
        "original": error_message,
        "category": "unknown",
        "suggestion": f"Unrecognized error. Check Avni server logs for details: {error_message[:200]}",
        "auto_fixable": False,
        "fix_action": None,
    }


def translate_multiple(errors: list[str]) -> list[dict]:
    """Translate a list of error messages."""
    return [translate_avni_error(e) for e in errors]
