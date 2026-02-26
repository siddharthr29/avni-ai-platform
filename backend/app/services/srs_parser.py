"""Parse Avni SRS Excel files into structured SRSData for bundle generation.

Supports two known SRS Excel layouts:
  - Simple (Sangwari-style): Group/Page Name, Field Name, Data Type, Mandatory,
    When to show, When NOT to show, Unique option, Default Value, OPTIONS, Validation
  - Expanded (Gubbachi-style): Page Name, Field Name, Data Type, Mandatory,
    User/System, Negative, Decimal, Min/Max, Unit, Current Date, Future Date,
    Past Date, Selection Type, OPTIONS, Unique option, Validation, Show, Not Show

Both layouts are auto-detected by inspecting the header row of each sheet.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

from app.models.schemas import (
    SRSData,
    SRSFormDefinition,
    SRSFormField,
    SRSFormGroup,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Mapping from SRS data-type strings (case-insensitive) to Avni concept types
_DATA_TYPE_MAP: dict[str, str] = {
    # Text variants
    "text": "Text",
    "short text": "Text",
    "long text": "Notes",
    "notes": "Notes",
    "note": "Notes",
    # Numeric
    "number": "Numeric",
    "numeric": "Numeric",
    "integer": "Numeric",
    "decimal": "Numeric",
    # Date / Time
    "date": "Date",
    "calender": "Date",
    "calendar": "Date",
    "datetime": "DateTime",
    "time": "Time",
    # Coded (single/multi select)
    "single select": "Coded",
    "multi select": "Coded",
    "multiselect": "Coded",
    "singleselect": "Coded",
    "dropdown": "Coded",
    "pre added options": "Coded",
    "pre-added options": "Coded",
    "coded": "Coded",
    # Media
    "image": "Image",
    "file": "File",
    "video": "Video",
    "audio": "Audio",
    # Phone
    "phone number": "PhoneNumber",
    "phonenumber": "PhoneNumber",
    "phone": "PhoneNumber",
    # Location
    "location": "Location",
    # Id
    "id": "Id",
    # Subject
    "subject": "Subject",
    # Question group
    "question group": "QuestionGroup",
    # Special
    "auto calculated": "Numeric",
}

# Known non-form sheet name patterns (case-insensitive substring matching)
_NON_FORM_PATTERNS: list[str] = [
    "help",
    "status tracker",
    "summary",
    "overview",
    "user persona",
    "user type",
    "w3h",
    "report",
    "bi report",
    "dashboard",
    "card",
    "permission",
    "privilege",
    "discussion",
    "decision",
    "issue",
    "review",
    "checklist",
    "modelling",
    "modeling",
    "location hierarchy",
    "subject type",
    "program encounter",
    "encounter",
    "other important",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize(val: Any) -> str | None:
    """Return stripped string or None."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalize_lower(val: Any) -> str:
    """Return lower-cased stripped string."""
    if val is None:
        return ""
    return str(val).strip().lower()


def _is_yes(val: Any) -> bool:
    """Check if a cell value means 'yes' / mandatory."""
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("yes", "y", "true", "1", "mandatory")


def _parse_options(raw: Any) -> list[str]:
    """Extract option strings from a cell value.

    Handles multiple real-world formats:
      - "a). Male\\nb). Female"
      - "Active\\nClosed"
      - "Option1; Option2; Option3"
      - "Option1, Option2, Option3"
      - "Option1/Option2/Option3"  (only when clearly a list)
      - "Yes/No"
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []

    options: list[str] = []

    # First try newline-separated (most common in real SRS files)
    lines = text.split("\n")
    if len(lines) > 1:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            # Strip "a). ", "b). ", "1. ", "- " prefixes
            cleaned = re.sub(r"^[a-z0-9]+\)\.\s*", "", line, flags=re.IGNORECASE)
            cleaned = re.sub(r"^[a-z0-9]+\)\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"^[-\u2022*]\s*", "", cleaned)
            cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
            cleaned = cleaned.strip()
            if cleaned:
                options.append(cleaned)
        if options:
            return options

    # Try semicolon-separated
    if ";" in text:
        for part in text.split(";"):
            part = part.strip()
            if part:
                options.append(part)
        if options:
            return options

    # Try slash-separated for short lists like "Yes/No", "Alcohol/Tobacco/None"
    if "/" in text and len(text) < 200:
        parts = [p.strip() for p in text.split("/") if p.strip()]
        if all(len(p) < 50 for p in parts) and len(parts) >= 2:
            return parts

    # Try comma-separated (last resort, risky for text with commas)
    if "," in text:
        parts = [p.strip() for p in text.split(",") if p.strip()]
        if len(parts) >= 2:
            return parts

    # Single value - strip any prefix
    cleaned = re.sub(r"^[a-z0-9]+\)\.\s*", "", text, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    if cleaned:
        return [cleaned]

    return []


def _parse_min_max(raw: Any) -> tuple[float | None, float | None]:
    """Try to extract min and max numeric bounds from a validation cell."""
    if raw is None:
        return None, None
    text = str(raw).strip()

    # Pattern: "Min: 0, Max: 200" or "0-200" or "Min 0 Max 200"
    m = re.search(r"min\s*[:=]?\s*(-?[\d.]+)", text, re.IGNORECASE)
    low = float(m.group(1)) if m else None

    m = re.search(r"max\s*[:=]?\s*(-?[\d.]+)", text, re.IGNORECASE)
    high = float(m.group(1)) if m else None

    if low is None and high is None:
        # Try "0-200" range pattern
        m = re.match(r"^(-?[\d.]+)\s*[-\u2013]\s*(-?[\d.]+)$", text)
        if m:
            low = float(m.group(1))
            high = float(m.group(2))

    return low, high


def _parse_unit(raw: Any) -> str | None:
    """Extract a unit string from a cell."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # Sometimes unit is in parentheses within the field name like "Weight (kg)"
    # This function handles explicit unit cells
    return text if text else None


def _extract_unit_from_name(name: str) -> tuple[str, str | None]:
    """Extract unit from field names like 'Weight (kg)' or 'MUAC (cm)'.

    Returns (cleaned_name, unit_or_none).
    """
    m = re.search(r"\(([a-zA-Z%/]+)\)\s*$", name)
    if m:
        unit = m.group(1).strip()
        cleaned = name[: m.start()].strip()
        return cleaned, unit
    return name, None


def _is_form_header_row(row: tuple) -> bool:
    """Check if a row looks like a form field header row."""
    # Normalize first few non-None values
    texts = []
    for val in row:
        if val is not None:
            texts.append(_normalize_lower(val))
        if len(texts) >= 5:
            break

    needed = {"field name", "data type"}
    found = set()
    for t in texts:
        for n in needed:
            if n in t:
                found.add(n)
    return len(found) >= 2


def _detect_column_indices(header_row: tuple) -> dict[str, int]:
    """Map logical column names to indices from the header row."""
    mapping: dict[str, int] = {}
    for i, val in enumerate(header_row):
        lower = _normalize_lower(val)
        if not lower:
            continue

        if "page" in lower or "group" in lower:
            mapping.setdefault("page_name", i)
        elif lower == "field name" or (lower.startswith("field") and "name" in lower):
            mapping.setdefault("field_name", i)
        elif lower == "data type" or lower.startswith("data type"):
            mapping.setdefault("data_type", i)
        elif "mandatory" in lower:
            mapping.setdefault("mandatory", i)
        elif "user enter" in lower or "system generat" in lower:
            mapping.setdefault("user_system", i)
        elif "negative" in lower:
            mapping.setdefault("allow_negative", i)
        elif "decimal" in lower:
            mapping.setdefault("allow_decimal", i)
        elif "max" in lower and "min" in lower and "limit" in lower:
            mapping.setdefault("min_max", i)
        elif "unit" in lower and "unique" not in lower:
            mapping.setdefault("unit", i)
        elif "selection type" in lower or "pre added options selection" in lower:
            mapping.setdefault("selection_type", i)
        elif "option" in lower and ("needed" in lower or "single" in lower or "multi" in lower):
            mapping.setdefault("options", i)
        elif lower.startswith("option") and "condition" not in lower and "unique" not in lower:
            mapping.setdefault("options", i)
        elif "unique option" in lower:
            mapping.setdefault("unique_option", i)
        elif "when to show" in lower or (lower.startswith("when") and "not" not in lower):
            mapping.setdefault("show_when", i)
        elif "when not" in lower or "not to show" in lower:
            mapping.setdefault("hide_when", i)
        elif "default" in lower:
            mapping.setdefault("default_value", i)
        elif "validation" in lower or "condition" in lower:
            mapping.setdefault("validation", i)

    return mapping


def _classify_sheet(name: str) -> str:
    """Classify a sheet by its name. Returns one of:
    'summary', 'user', 'w3h', 'form', 'report', 'dashboard',
    'permission', 'modelling', 'skip', or 'unknown'.
    """
    lower = name.strip().lower()

    if "help" in lower or "status tracker" in lower:
        return "skip"
    if "summary" in lower or "overview" in lower:
        return "summary"
    if "user" in lower and ("type" in lower or "persona" in lower):
        return "user"
    if "w3h" in lower:
        return "w3h"
    if "report" in lower or "bi report" in lower:
        return "report"
    if "dashboard" in lower or "card" in lower:
        return "dashboard"
    if "permission" in lower or "privilege" in lower:
        return "permission"
    if "model" in lower:
        return "modelling"
    if "location" in lower and "hierarch" in lower:
        return "location"
    if "program encounter" in lower:
        return "program_encounters"
    if lower.strip() in ("program", "programs"):
        return "programs_meta"
    if lower.strip() in ("encounter", "encounters"):
        return "encounters_meta"
    if "subject type" in lower:
        return "subject_types"
    if "discussion" in lower or "decision" in lower or "issue" in lower:
        return "skip"
    if "review" in lower or "checklist" in lower:
        return "skip"
    if "other important" in lower:
        return "skip"

    return "unknown"


# ---------------------------------------------------------------------------
# Sheet Parsers
# ---------------------------------------------------------------------------


def _parse_summary_sheet(ws: Worksheet) -> dict[str, Any]:
    """Parse a Project Summary / Program Summary sheet.

    Returns dict with keys: org_name, location_hierarchy, programs_text, etc.
    """
    result: dict[str, Any] = {}

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        label = _normalize_lower(row[0]) if row and len(row) > 0 else ""
        value = _normalize(row[1]) if row and len(row) > 1 else None

        if not label or not value:
            continue

        if "organisation" in label or "organization" in label:
            result["org_name"] = value
        elif "program name" in label or "name of the program" in label:
            result["org_name"] = result.get("org_name") or value
            result["program_name"] = value
        elif "location hierarchy" in label or "location" in label and "hierarchy" in label:
            result["location_hierarchy"] = value
        elif "geographical" in label:
            result["geography"] = value
        elif "project" in label and "portfolio" in label:
            result["programs_text"] = value
        elif "number of user" in label:
            result["users_text"] = value
        elif "beneficiar" in label:
            result["beneficiaries_text"] = value
        elif "objective" in label:
            result["objective"] = value
        elif "name of the program" in label:
            result["program_name"] = value

    return result


def _parse_user_sheet(ws: Worksheet) -> list[str]:
    """Parse User Types / User Persona sheet. Returns list of group names."""
    groups: list[str] = []
    first_data_row = True

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        user_type = _normalize(row[0]) if row and len(row) > 0 else None
        if not user_type:
            continue

        lower = user_type.lower()
        # Skip header row
        if "user type" in lower or "user persona" in lower:
            first_data_row = True
            continue

        # Extract just the primary name (before newlines/parentheses)
        name = user_type.split("\n")[0].strip()
        name = re.sub(r"\s*\(.*?\)\s*", "", name).strip()
        if name and name.lower() not in ("user type", "description", "number"):
            groups.append(name)

    return groups


def _parse_w3h_sheet(ws: Worksheet) -> list[dict[str, Any]]:
    """Parse W3H sheet. Returns list of activity dicts with keys:
    what, when, who, how, schedule, notes.
    """
    activities: list[dict[str, Any]] = []

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        what = _normalize(row[0]) if row and len(row) > 0 else None
        if not what:
            continue
        if what.lower() in ("what", "activity"):
            continue  # header row

        activity: dict[str, Any] = {"what": what}
        if len(row) > 1:
            activity["when"] = _normalize(row[1])
        if len(row) > 2:
            activity["who"] = _normalize(row[2])
        if len(row) > 3:
            activity["how"] = _normalize(row[3])
        if len(row) > 4:
            activity["schedule"] = _normalize(row[4])
        if len(row) > 5:
            activity["notes"] = _normalize(row[5])
        activities.append(activity)

    return activities


def _parse_permission_sheet(ws: Worksheet) -> tuple[list[str], dict[str, Any]]:
    """Parse Permissions sheet.

    Returns (group_names, permission_matrix).
    group_names: list of group/role names from the header.
    permission_matrix: dict keyed by form name -> dict of privilege -> dict of group -> bool.
    """
    groups: list[str] = []
    matrix: dict[str, Any] = {}

    header_row = None
    group_start_col = 2  # default: groups start at column C (index 2)

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True), 1):
        vals = list(row)

        # Detect header
        if header_row is None:
            label0 = _normalize_lower(vals[0]) if vals else ""
            if "form" in label0 or "privilege" in label0:
                # Find where groups start
                for i, v in enumerate(vals):
                    vl = _normalize_lower(v)
                    if vl and vl not in ("form", "privileges", "privilege"):
                        group_start_col = i
                        break
                groups = [
                    _normalize(v)
                    for v in vals[group_start_col:]
                    if _normalize(v) is not None
                ]
                header_row = row_idx
                continue
            continue

        # Data rows
        form_name = _normalize(vals[0])
        privilege = _normalize(vals[1]) if len(vals) > 1 else None

        # Form name may be in previous row (merged cells pattern)
        if form_name and privilege:
            current_form = form_name
        elif not form_name and privilege:
            # Use last known form name
            pass
        else:
            continue

        if not privilege:
            continue

        if form_name:
            current_form = form_name

        if current_form not in matrix:
            matrix[current_form] = {}

        priv_grants: dict[str, bool] = {}
        for gi, group in enumerate(groups):
            col_idx = group_start_col + gi
            val = _normalize_lower(vals[col_idx]) if col_idx < len(vals) else ""
            priv_grants[group] = val in ("yes", "y", "true", "1")

        matrix[current_form][privilege] = priv_grants

    return groups, matrix


def _parse_location_hierarchy_sheet(ws: Worksheet) -> list[dict[str, Any]]:
    """Parse a Location Hierarchy sheet.

    Returns list of dicts with keys: name, level, parent (optional).
    """
    levels: list[dict[str, Any]] = []

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True):
        name = _normalize(row[0]) if row and len(row) > 0 else None
        if not name:
            continue
        lower = name.lower()
        if "location" in lower and ("type" in lower or "hierarchy" in lower):
            continue  # header

        # Clean up "District / Region:" style names
        cleaned = re.sub(r"\s*[/:].*$", "", name).strip()
        if cleaned:
            levels.append({"name": cleaned})

    # Assign levels (highest number = top of hierarchy)
    total = len(levels)
    for i, level in enumerate(levels):
        level["level"] = total - i
        if i > 0:
            level["parent"] = levels[i - 1]["name"]

    return levels


def _parse_programs_meta_sheet(ws: Worksheet) -> list[dict[str, Any]]:
    """Parse a Programs metadata sheet (Modelling-style).

    Returns list of dicts with keys: name, enrolment_form, exit_form.
    """
    programs: list[dict[str, Any]] = []

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        name = _normalize(row[0]) if row and len(row) > 0 else None
        if not name:
            continue
        prog: dict[str, Any] = {"name": name}
        if len(row) > 1 and _normalize(row[1]):
            prog["enrolment_form"] = _normalize(row[1])
        if len(row) > 2 and _normalize(row[2]):
            prog["exit_form"] = _normalize(row[2])
        programs.append(prog)

    return programs


def _parse_program_encounters_sheet(ws: Worksheet) -> list[dict[str, Any]]:
    """Parse a Program Encounters metadata sheet.

    Returns list of dicts with: encounter_name, program_name, form_name, cancellation_form.
    """
    mappings: list[dict[str, Any]] = []

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        enc_name = _normalize(row[0]) if row and len(row) > 0 else None
        if not enc_name:
            continue
        mapping: dict[str, Any] = {"encounter_name": enc_name}
        if len(row) > 1 and _normalize(row[1]):
            mapping["program_name"] = _normalize(row[1])
        if len(row) > 3 and _normalize(row[3]):
            mapping["form_name"] = _normalize(row[3])
        if len(row) > 4 and _normalize(row[4]):
            mapping["cancellation_form"] = _normalize(row[4])
        mappings.append(mapping)

    return mappings


def _parse_modelling_sheet(ws: Worksheet) -> dict[str, Any]:
    """Parse a Modelling sheet.

    Returns dict with: subject_types, programs, encounters.
    """
    subject_types: list[dict[str, Any]] = []
    programs: list[dict[str, Any]] = []
    encounters: list[dict[str, Any]] = []

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        row_type = _normalize_lower(row[0]) if row and len(row) > 0 else ""
        name = _normalize(row[1]) if len(row) > 1 else None
        if not name:
            continue

        if row_type == "subject":
            st: dict[str, Any] = {"name": name}
            if len(row) > 2 and _normalize(row[2]):
                st["type"] = _normalize(row[2])
            subject_types.append(st)
        elif row_type == "program":
            prog: dict[str, Any] = {"name": name}
            if len(row) > 4 and _normalize(row[4]):
                prog["colour"] = _normalize(row[4])
            programs.append(prog)
        elif row_type == "encounter":
            enc: dict[str, Any] = {"name": name}
            if len(row) > 2 and _normalize(row[2]):
                enc["subject_type"] = _normalize(row[2])
            if len(row) > 6 and _normalize(row[6]):
                enc["program"] = _normalize(row[6])
            if len(row) > 7 and _normalize(row[7]):
                enc["encounter_type"] = _normalize(row[7])
            encounters.append(enc)

    return {
        "subject_types": subject_types,
        "programs": programs,
        "encounters": encounters,
    }


def _parse_form_sheet(
    ws: Worksheet,
    sheet_name: str,
) -> SRSFormDefinition | None:
    """Parse a single form sheet into an SRSFormDefinition.

    Auto-detects the header row by looking for "Field Name" and "Data Type".
    Groups fields by the Page/Group Name column.
    """
    # Find header row
    header_row_idx: int | None = None
    header_row_data: tuple | None = None

    for row_idx, row in enumerate(ws.iter_rows(min_row=1, max_row=min(5, ws.max_row), values_only=True), 1):
        if _is_form_header_row(row):
            header_row_idx = row_idx
            header_row_data = row
            break

    if header_row_idx is None or header_row_data is None:
        logger.debug("Sheet '%s' has no form header row, skipping", sheet_name)
        return None

    cols = _detect_column_indices(header_row_data)
    if "field_name" not in cols or "data_type" not in cols:
        logger.debug("Sheet '%s' missing field_name/data_type columns, skipping", sheet_name)
        return None

    # Parse data rows
    groups_ordered: list[str] = []
    groups_fields: dict[str, list[SRSFormField]] = {}
    current_group = "Default"
    skip_row_patterns = {"tb patients form"}

    for row in ws.iter_rows(min_row=header_row_idx + 1, max_row=ws.max_row, values_only=True):
        vals = list(row)

        # Extract page/group name
        page_val = _normalize(vals[cols["page_name"]]) if "page_name" in cols and cols["page_name"] < len(vals) else None
        field_name = _normalize(vals[cols["field_name"]]) if cols["field_name"] < len(vals) else None
        data_type_raw = _normalize(vals[cols["data_type"]]) if cols["data_type"] < len(vals) else None

        # Update current group from page name column
        if page_val:
            current_group = page_val

        # Skip rows with no field name
        if not field_name:
            continue

        # Skip known noise rows (sub-headers within forms)
        if field_name.lower() in skip_row_patterns:
            continue
        # Skip rows where "field name" looks like a sub-heading (no data type)
        if not data_type_raw:
            # Sometimes the field name IS a section header if data_type is missing
            # But only skip if it looks like a title
            if page_val and page_val.lower() == field_name.lower():
                continue
            # Field with no data type -- skip
            continue

        # Map data type
        dt_lower = data_type_raw.lower().strip()
        avni_type = _DATA_TYPE_MAP.get(dt_lower, "Text")

        # Determine if mandatory
        mandatory = False
        if "mandatory" in cols and cols["mandatory"] < len(vals):
            mandatory = _is_yes(vals[cols["mandatory"]])

        # Determine selection type (SingleSelect / MultiSelect)
        selection_type: str | None = None
        if "selection_type" in cols and cols["selection_type"] < len(vals):
            sel = _normalize_lower(vals[cols["selection_type"]])
            if "multi" in sel:
                selection_type = "MultiSelect"
            elif "single" in sel:
                selection_type = "SingleSelect"

        # Infer selection type from data type if not set
        if avni_type == "Coded" and selection_type is None:
            if "multi" in dt_lower:
                selection_type = "MultiSelect"
            else:
                selection_type = "SingleSelect"

        # Parse options
        options: list[str] = []
        if "options" in cols and cols["options"] < len(vals):
            raw_opt = _normalize(vals[cols["options"]])
            # Guard: if the OPTIONS column contains a selection type value
            # (e.g. "Single Select", "Multi Select"), it's misaligned data.
            # In that case, read the selection type from this column and
            # look one column to the right for the actual options.
            if raw_opt and raw_opt.lower().strip() in (
                "single select", "multi select", "singleselect", "multiselect",
                "single", "multi",
            ):
                if "multi" in raw_opt.lower():
                    selection_type = "MultiSelect"
                else:
                    selection_type = "SingleSelect"
                # Try the next column for actual options
                next_col = cols["options"] + 1
                if next_col < len(vals):
                    options = _parse_options(vals[next_col])
            else:
                options = _parse_options(raw_opt)

        # If no options found in the options column but the selection_type column
        # contains what look like actual option values (Gubbachi misalignment)
        if not options and avni_type == "Coded":
            if "selection_type" in cols and cols["selection_type"] < len(vals):
                sel_raw = _normalize(vals[cols["selection_type"]])
                if sel_raw and sel_raw.lower().strip() not in (
                    "single select", "multi select", "singleselect", "multiselect",
                    "single", "multi", "",
                ):
                    # The selection_type column has actual option values
                    candidate_opts = _parse_options(sel_raw)
                    if len(candidate_opts) >= 2:
                        options = candidate_opts

        # Parse unit
        unit: str | None = None
        if "unit" in cols and cols["unit"] < len(vals):
            unit = _parse_unit(vals[cols["unit"]])

        # Extract unit from field name if not set
        if not unit and avni_type == "Numeric":
            field_name, extracted_unit = _extract_unit_from_name(field_name)
            if extracted_unit:
                unit = extracted_unit

        # Parse min/max
        low: float | None = None
        high: float | None = None
        if "min_max" in cols and cols["min_max"] < len(vals):
            low, high = _parse_min_max(vals[cols["min_max"]])
        # Also check validation column
        if low is None and high is None and "validation" in cols and cols["validation"] < len(vals):
            low, high = _parse_min_max(vals[cols["validation"]])

        # Build key values for skip logic
        key_values: list[dict[str, Any]] = []

        # Show when / hide when
        show_when = None
        hide_when = None
        if "show_when" in cols and cols["show_when"] < len(vals):
            show_when = _normalize(vals[cols["show_when"]])
        if "hide_when" in cols and cols["hide_when"] < len(vals):
            hide_when = _normalize(vals[cols["hide_when"]])

        if show_when:
            key_values.append({"key": "showWhen", "value": show_when})
        if hide_when:
            key_values.append({"key": "hideWhen", "value": hide_when})

        # Unique option for multi-select
        if "unique_option" in cols and cols["unique_option"] < len(vals):
            unique_opt = _normalize(vals[cols["unique_option"]])
            if unique_opt:
                key_values.append({"key": "ExcludedAnswers", "value": unique_opt})

        # Build field
        field = SRSFormField(
            name=field_name,
            dataType=avni_type,
            mandatory=mandatory,
            options=options if options else None,
            type=selection_type,
            unit=unit,
            lowAbsolute=low,
            highAbsolute=high,
            keyValues=key_values if key_values else None,
        )

        # Add to group
        if current_group not in groups_fields:
            groups_ordered.append(current_group)
            groups_fields[current_group] = []
        groups_fields[current_group].append(field)

    # Build form definition
    if not groups_fields:
        logger.debug("Sheet '%s' has no parseable fields, skipping", sheet_name)
        return None

    form_groups = [
        SRSFormGroup(name=gname, fields=groups_fields[gname])
        for gname in groups_ordered
    ]

    return SRSFormDefinition(
        name=sheet_name.strip(),
        formType="ProgramEncounter",  # Will be refined later
        groups=form_groups,
    )


# ---------------------------------------------------------------------------
# Main Parser
# ---------------------------------------------------------------------------


class SRSParser:
    """Parse Avni SRS Excel files into structured SRSData."""

    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self.wb = openpyxl.load_workbook(str(file_path), data_only=True)
        self.sheet_names = self.wb.sheetnames

        # Intermediate state
        self._summary: dict[str, Any] = {}
        self._user_groups: list[str] = []
        self._w3h: list[dict[str, Any]] = []
        self._forms: list[SRSFormDefinition] = []
        self._permission_groups: list[str] = []
        self._permission_matrix: dict[str, Any] = {}
        self._location_hierarchy: list[dict[str, Any]] = []
        self._modelling: dict[str, Any] = {}
        self._programs_meta: list[dict[str, Any]] = []
        self._program_encounters_meta: list[dict[str, Any]] = []
        self._encounters_meta: list[dict[str, Any]] = []

    def parse(self) -> SRSData:
        """Parse the complete SRS workbook into SRSData."""
        logger.info("Parsing SRS file: %s (%d sheets)", self.file_path.name, len(self.sheet_names))

        # Classify and parse each sheet
        for name in self.sheet_names:
            ws = self.wb[name]
            classification = _classify_sheet(name)
            logger.debug("Sheet '%s' classified as '%s'", name, classification)

            if classification == "skip":
                continue
            elif classification == "summary":
                self._summary = _parse_summary_sheet(ws)
            elif classification == "user":
                self._user_groups = _parse_user_sheet(ws)
            elif classification == "w3h":
                self._w3h = _parse_w3h_sheet(ws)
            elif classification == "permission":
                self._permission_groups, self._permission_matrix = _parse_permission_sheet(ws)
            elif classification == "location":
                self._location_hierarchy = _parse_location_hierarchy_sheet(ws)
            elif classification == "programs_meta":
                self._programs_meta = _parse_programs_meta_sheet(ws)
            elif classification == "program_encounters":
                self._program_encounters_meta = _parse_program_encounters_sheet(ws)
            elif classification == "encounters_meta":
                self._encounters_meta = []
                for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
                    enc_name = _normalize(row[0]) if row and len(row) > 0 else None
                    if enc_name:
                        self._encounters_meta.append({"name": enc_name})
            elif classification == "modelling":
                self._modelling = _parse_modelling_sheet(ws)
            elif classification == "report" or classification == "dashboard":
                # Informational only -- skip for bundle generation
                continue
            else:
                # Unknown sheet -- try to parse as a form
                form_def = _parse_form_sheet(ws, name)
                if form_def:
                    self._forms.append(form_def)
                    logger.info(
                        "Parsed form sheet '%s': %d groups, %d fields",
                        name,
                        len(form_def.groups),
                        sum(len(g.fields) for g in form_def.groups),
                    )

        # Assemble SRSData
        return self._build_srs_data()

    def _build_srs_data(self) -> SRSData:
        """Assemble parsed data into an SRSData instance."""
        # Organization name
        org_name = (
            self._summary.get("org_name")
            or self._summary.get("program_name")
            or self.file_path.stem
        )

        # Subject types
        subject_types: list[dict[str, Any]] = []
        if self._modelling.get("subject_types"):
            for st in self._modelling["subject_types"]:
                subject_types.append({
                    "name": st["name"],
                    "type": st.get("type", "Person"),
                })
        if not subject_types:
            subject_types = [{"name": "Individual", "type": "Person"}]

        # Programs -- from modelling, programs_meta, or infer from W3H/form names
        programs = self._resolve_programs()

        # Encounter types -- collected from form classification
        encounter_types = self._resolve_encounter_types()

        # Classify forms (set correct formType, programName, encounterTypeName)
        self._classify_forms(programs, encounter_types)

        # All unique encounter type names
        all_encounter_names: list[str] = []
        seen_enc: set[str] = set()
        for form_def in self._forms:
            if form_def.encounterTypeName and form_def.encounterTypeName not in seen_enc:
                all_encounter_names.append(form_def.encounterTypeName)
                seen_enc.add(form_def.encounterTypeName)

        # Groups
        groups = self._resolve_groups()

        # Address level types
        address_level_types = self._resolve_address_levels()

        # Program-encounter mappings
        pe_mappings = self._resolve_program_encounter_mappings()

        # General encounter types (no program)
        general_encounter_types = self._resolve_general_encounter_types()

        return SRSData(
            orgName=org_name,
            subjectTypes=subject_types,
            programs=[{"name": p} if isinstance(p, str) else p for p in programs],
            encounterTypes=all_encounter_names,
            forms=self._forms,
            groups=groups,
            addressLevelTypes=address_level_types if address_level_types else None,
            programEncounterMappings=pe_mappings if pe_mappings else None,
            generalEncounterTypes=general_encounter_types if general_encounter_types else None,
        )

    def _resolve_programs(self) -> list[dict[str, Any]]:
        """Determine program list from available data sources."""
        programs: list[dict[str, Any]] = []
        seen: set[str] = set()

        # From modelling sheet
        for p in self._modelling.get("programs", []):
            name = p["name"].strip()
            if name not in seen:
                prog: dict[str, Any] = {"name": name}
                if p.get("colour"):
                    prog["colour"] = p["colour"]
                programs.append(prog)
                seen.add(name)

        # From programs meta sheet
        for p in self._programs_meta:
            name = p["name"].strip()
            if name not in seen:
                programs.append({"name": name})
                seen.add(name)

        # Infer from W3H (enrollment/exit activities suggest programs)
        if not programs:
            programs = self._infer_programs_from_sheets()

        return programs

    def _infer_programs_from_sheets(self) -> list[dict[str, Any]]:
        """Infer programs from form sheet names.

        Heuristic: sheets named "X Enrollment" suggest a program called "X Program"
        or similar.
        """
        programs: list[dict[str, Any]] = []
        seen: set[str] = set()

        enrollment_pattern = re.compile(
            r"^(.+?)\s*(enroll?ment|enrol)\s*$", re.IGNORECASE
        )

        for name in self.sheet_names:
            m = enrollment_pattern.match(name.strip())
            if m:
                prog_base = m.group(1).strip()
                # Check if there's a matching exit sheet
                prog_name = prog_base
                if prog_name not in seen:
                    programs.append({"name": prog_name})
                    seen.add(prog_name)

        return programs

    def _resolve_encounter_types(self) -> dict[str, str]:
        """Build encounter_name -> form_type mapping.

        Returns dict: encounter_type_name -> Avni form type.
        """
        encounters: dict[str, str] = {}

        # From modelling sheet
        for enc in self._modelling.get("encounters", []):
            name = enc["name"]
            etype = enc.get("encounter_type", "ProgramEncounter")
            encounters[name] = etype

        # From program encounters meta
        for pe in self._program_encounters_meta:
            name = pe["encounter_name"]
            if name not in encounters:
                encounters[name] = "ProgramEncounter"

        # From general encounters meta
        for enc in self._encounters_meta:
            name = enc["name"]
            if name not in encounters:
                encounters[name] = "Encounter"

        return encounters

    def _classify_forms(
        self,
        programs: list[dict[str, Any]],
        encounter_types: dict[str, str],
    ) -> None:
        """Assign formType, programName, encounterTypeName to each parsed form."""
        program_names = {p["name"].strip().lower(): p["name"].strip() for p in programs}

        # Build program encounter mapping from meta
        pe_map: dict[str, str] = {}  # encounter_name -> program_name
        for pe in self._program_encounters_meta:
            enc = pe["encounter_name"].strip()
            prog = pe.get("program_name", "").strip()
            if prog:
                pe_map[enc.lower()] = prog
        for enc in self._modelling.get("encounters", []):
            prog = enc.get("program", "")
            if prog:
                pe_map[enc["name"].strip().lower()] = prog

        # Build program enrolment/exit form names from meta
        prog_enrol_forms: dict[str, str] = {}  # form_name_lower -> program_name
        prog_exit_forms: dict[str, str] = {}
        for pm in self._programs_meta:
            pname = pm["name"].strip()
            if pm.get("enrolment_form"):
                prog_enrol_forms[pm["enrolment_form"].strip().lower()] = pname
            if pm.get("exit_form"):
                prog_exit_forms[pm["exit_form"].strip().lower()] = pname

        for form_def in self._forms:
            name_lower = form_def.name.strip().lower()

            # 1. Registration forms
            if "registration" in name_lower or "individual registration" in name_lower:
                form_def.formType = "IndividualProfile"
                continue

            # 2. Check enrolment form from meta
            if name_lower in prog_enrol_forms:
                form_def.formType = "ProgramEnrolment"
                form_def.programName = prog_enrol_forms[name_lower]
                continue

            # 3. Check exit form from meta
            if name_lower in prog_exit_forms:
                form_def.formType = "ProgramExit"
                form_def.programName = prog_exit_forms[name_lower]
                continue

            # 4. Check if encounter type from modelling/meta
            if name_lower in encounter_types:
                etype = encounter_types[name_lower]
                form_def.formType = etype
                form_def.encounterTypeName = form_def.name.strip()
                if name_lower in pe_map:
                    form_def.programName = pe_map[name_lower]
                continue

            # 5. Heuristic: "X Enrollment" / "X Enrolment" -> ProgramEnrolment
            enrol_match = re.match(r"^(.+?)\s*(enroll?ment|enrol)\s*$", name_lower)
            if enrol_match:
                base = enrol_match.group(1).strip()
                form_def.formType = "ProgramEnrolment"
                # Try to match to a program
                form_def.programName = self._find_matching_program(base, program_names)
                continue

            # 6. Heuristic: "X Exit" -> ProgramExit
            exit_match = re.match(r"^(.+?)\s*exit\s*$", name_lower)
            if exit_match:
                base = exit_match.group(1).strip()
                form_def.formType = "ProgramExit"
                form_def.programName = self._find_matching_program(base, program_names)
                continue

            # 7. Heuristic: "X Follow Up" / "X Screening" / "X Check Up" -> ProgramEncounter
            encounter_match = re.match(
                r"^(.+?)\s*(follow\s*up|screening|check\s*up|health\s*check)\s*$",
                name_lower,
            )
            if encounter_match:
                form_def.formType = "ProgramEncounter"
                form_def.encounterTypeName = form_def.name.strip()
                # Try to find which program this belongs to
                base = encounter_match.group(1).strip()
                if name_lower in pe_map:
                    form_def.programName = pe_map[name_lower]
                else:
                    form_def.programName = self._find_matching_program(base, program_names)
                continue

            # 8. Heuristic: "X Cancellation" -> ProgramEncounterCancellation or IndividualEncounterCancellation
            cancel_match = re.match(r"^(.+?)\s*cancell?ation\s*$", name_lower)
            if cancel_match:
                base_name = cancel_match.group(1).strip()
                # Check if there's a program encounter with this base name
                if base_name.lower() in pe_map:
                    form_def.formType = "ProgramEncounterCancellation"
                    form_def.encounterTypeName = base_name
                    form_def.programName = pe_map[base_name.lower()]
                else:
                    form_def.formType = "IndividualEncounterCancellation"
                    form_def.encounterTypeName = base_name
                continue

            # 9. Default: Encounter (general encounter)
            form_def.formType = "Encounter"
            form_def.encounterTypeName = form_def.name.strip()

    def _find_matching_program(
        self,
        base: str,
        program_names: dict[str, str],
    ) -> str | None:
        """Find a program name that matches a base string.

        Uses fuzzy substring matching.
        """
        base_lower = base.lower().strip()

        # Exact match
        if base_lower in program_names:
            return program_names[base_lower]

        # Check if base is a prefix of any program
        for pname_lower, pname in program_names.items():
            if pname_lower.startswith(base_lower) or base_lower.startswith(pname_lower):
                return pname

        # Check if any word from base appears in program names
        base_words = set(base_lower.split())
        best_match: str | None = None
        best_score = 0
        for pname_lower, pname in program_names.items():
            pwords = set(pname_lower.split())
            overlap = len(base_words & pwords)
            if overlap > best_score:
                best_score = overlap
                best_match = pname

        if best_score > 0:
            return best_match

        # Last resort: first program
        if program_names:
            return next(iter(program_names.values()))

        return None

    def _resolve_groups(self) -> list[str]:
        """Determine user groups from all sources."""
        groups: list[str] = []
        seen: set[str] = set()

        # Always include "Everyone"
        groups.append("Everyone")
        seen.add("everyone")

        # From user sheet
        for g in self._user_groups:
            gl = g.lower()
            if gl not in seen:
                groups.append(g)
                seen.add(gl)

        # From permissions sheet
        for g in self._permission_groups:
            gl = g.lower()
            if gl not in seen:
                groups.append(g)
                seen.add(gl)

        return groups

    def _resolve_address_levels(self) -> list[dict[str, Any]]:
        """Determine address level types."""
        if self._location_hierarchy:
            return self._location_hierarchy

        # Try to extract from summary
        hierarchy_text = self._summary.get("location_hierarchy", "")
        if hierarchy_text:
            return self._parse_hierarchy_text(hierarchy_text)

        return []

    def _parse_hierarchy_text(self, text: str) -> list[dict[str, Any]]:
        """Parse a location hierarchy from text like 'Block -> Village -> Para'
        or 'State: Karnataka\\nDistrict: Bengaluru'.
        """
        levels: list[dict[str, Any]] = []

        # Try arrow-separated: "Block -> Village -> Para"
        if "->" in text:
            parts = [p.strip() for p in text.split("->") if p.strip()]
            total = len(parts)
            for i, part in enumerate(parts):
                level_entry: dict[str, Any] = {
                    "name": part,
                    "level": total - i,
                }
                if i > 0:
                    level_entry["parent"] = parts[i - 1]
                levels.append(level_entry)
            return levels

        # Try colon-separated lines: "State: Karnataka\nDistrict: Bengaluru"
        lines = text.split("\n")
        for line in lines:
            line = line.strip().lstrip("\u2022\t -")
            if ":" in line:
                name = line.split(":")[0].strip()
                name = re.sub(r"\s*/.*$", "", name).strip()  # Remove "/ Region" etc.
                if name:
                    levels.append({"name": name})

        total = len(levels)
        for i, level_entry in enumerate(levels):
            level_entry["level"] = total - i
            if i > 0:
                level_entry["parent"] = levels[i - 1]["name"]

        return levels

    def _resolve_program_encounter_mappings(self) -> list[dict[str, Any]]:
        """Build program-encounter type mappings."""
        pe_map: dict[str, set[str]] = {}

        # From parsed forms
        for form_def in self._forms:
            if form_def.formType in ("ProgramEncounter", "ProgramEncounterCancellation"):
                if form_def.programName and form_def.encounterTypeName:
                    pe_map.setdefault(form_def.programName, set()).add(
                        form_def.encounterTypeName
                    )

        # From program encounters meta
        for pe in self._program_encounters_meta:
            prog = pe.get("program_name", "").strip()
            enc = pe["encounter_name"].strip()
            if prog:
                pe_map.setdefault(prog, set()).add(enc)

        return [
            {"program": prog, "encounterTypes": sorted(ets)}
            for prog, ets in pe_map.items()
        ]

    def _resolve_general_encounter_types(self) -> list[str]:
        """Find encounter types not linked to any program."""
        general: list[str] = []
        for form_def in self._forms:
            if form_def.formType in ("Encounter", "IndividualEncounterCancellation"):
                if form_def.encounterTypeName:
                    if form_def.encounterTypeName not in general:
                        general.append(form_def.encounterTypeName)
        return general


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def parse_srs_excel(file_path: str | Path) -> SRSData:
    """Parse an SRS Excel file and return structured SRSData.

    This is the primary entry point for use by other modules.
    """
    parser = SRSParser(file_path)
    return parser.parse()
