"""Natural language bundle editing service.

Parses natural language instructions into structured edit commands and applies
them to generated bundle files on disk. Supports deterministic parsing for
common patterns (rename, add, remove, make mandatory, change type, add/remove
option) and falls back to LLM parsing for complex or ambiguous instructions.

Usage:
    from app.services.bundle_editor import edit_bundle_nl

    result = await edit_bundle_nl("bundle-123", "rename field 'Weight' to 'Body Weight'")
"""

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class BundleEditCommand:
    """A single structured edit operation on a bundle."""

    action: str  # rename_field, add_field, remove_field, make_mandatory,
    #               make_optional, change_type, add_option, remove_option
    target_field: str  # concept/field name to modify
    target_form: str | None = None  # specific form name, or None for all
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        """Human-readable summary of this command."""
        descriptions = {
            "rename_field": f"Rename '{self.target_field}' to '{self.params.get('new_name', '?')}'",
            "add_field": (
                f"Add field '{self.target_field}' "
                f"(type={self.params.get('data_type', 'Text')})"
            ),
            "remove_field": f"Remove field '{self.target_field}'",
            "make_mandatory": f"Make '{self.target_field}' mandatory",
            "make_optional": f"Make '{self.target_field}' optional",
            "change_type": (
                f"Change data type of '{self.target_field}' "
                f"to '{self.params.get('new_type', '?')}'"
            ),
            "add_option": (
                f"Add option(s) {self.params.get('options', [])} "
                f"to '{self.target_field}'"
            ),
            "remove_option": (
                f"Remove option(s) {self.params.get('options', [])} "
                f"from '{self.target_field}'"
            ),
        }
        base = descriptions.get(self.action, f"{self.action} on '{self.target_field}'")
        if self.target_form:
            base += f" (in form '{self.target_form}')"
        return base


# Valid actions
VALID_ACTIONS = {
    "rename_field", "add_field", "remove_field",
    "make_mandatory", "make_optional",
    "change_type", "add_option", "remove_option",
}

# Avni data types
AVNI_DATA_TYPES = {
    "text": "Text",
    "numeric": "Numeric",
    "number": "Numeric",
    "date": "Date",
    "datetime": "DateTime",
    "time": "Time",
    "coded": "Coded",
    "notes": "Notes",
    "image": "Image",
    "video": "Video",
    "audio": "Audio",
    "file": "File",
    "phonenumber": "PhoneNumber",
    "phone number": "PhoneNumber",
    "phone": "PhoneNumber",
    "location": "Location",
    "duration": "Duration",
    "id": "Id",
    "na": "NA",
    "subject": "Subject",
}


# ---------------------------------------------------------------------------
# Deterministic parser — handles common patterns without LLM
# ---------------------------------------------------------------------------

def _strip_quotes(s: str) -> str:
    """Remove surrounding quotes (single or double) from a string."""
    s = s.strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        return s[1:-1]
    return s


def _parse_options_list(text: str) -> list[str]:
    """Parse a comma-separated list of options, handling quoted values."""
    options = []
    for part in re.split(r",\s*", text.strip()):
        cleaned = _strip_quotes(part.strip())
        if cleaned:
            options.append(cleaned)
    return options


def _normalize_data_type(raw: str) -> str | None:
    """Convert user-provided data type to Avni canonical type."""
    return AVNI_DATA_TYPES.get(raw.strip().lower())


# Each pattern returns (action, target_field, target_form, params) or None
_DETERMINISTIC_PATTERNS: list[
    tuple[re.Pattern, callable]
] = []


def _register_pattern(pattern: str, flags: int = re.IGNORECASE):
    """Decorator to register a deterministic parsing pattern."""
    compiled = re.compile(pattern, flags)

    def decorator(fn):
        _DETERMINISTIC_PATTERNS.append((compiled, fn))
        return fn

    return decorator


@_register_pattern(
    r"rename\s+(?:field\s+)?['\"](.+?)['\"]\s+to\s+['\"](.+?)['\"]"
)
def _parse_rename(m: re.Match) -> BundleEditCommand:
    return BundleEditCommand(
        action="rename_field",
        target_field=m.group(1),
        params={"new_name": m.group(2)},
    )


@_register_pattern(
    r"add\s+(?:field\s+)?['\"](.+?)['\"]\s+(?:with|having)\s+options?\s+(.+)"
)
def _parse_add_coded(m: re.Match) -> BundleEditCommand:
    options = _parse_options_list(m.group(2))
    return BundleEditCommand(
        action="add_field",
        target_field=m.group(1),
        params={"data_type": "Coded", "options": options},
    )


@_register_pattern(
    r"add\s+(?:field\s+)?['\"](.+?)['\"]\s+(?:as|of\s+type|with\s+type)\s+(\w+)"
)
def _parse_add_typed(m: re.Match) -> BundleEditCommand:
    data_type = _normalize_data_type(m.group(2)) or "Text"
    return BundleEditCommand(
        action="add_field",
        target_field=m.group(1),
        params={"data_type": data_type},
    )


@_register_pattern(
    r"add\s+(?:field\s+)?['\"](.+?)['\"]$"
)
def _parse_add_simple(m: re.Match) -> BundleEditCommand:
    return BundleEditCommand(
        action="add_field",
        target_field=m.group(1),
        params={"data_type": "Text"},
    )


@_register_pattern(
    r"(?:remove|delete)\s+(?:field\s+)?['\"](.+?)['\"]"
)
def _parse_remove(m: re.Match) -> BundleEditCommand:
    return BundleEditCommand(
        action="remove_field",
        target_field=m.group(1),
    )


@_register_pattern(
    r"make\s+['\"](.+?)['\"]\s+mandatory|['\"](.+?)['\"]\s+should\s+be\s+mandatory"
)
def _parse_mandatory(m: re.Match) -> BundleEditCommand:
    field_name = m.group(1) or m.group(2)
    return BundleEditCommand(
        action="make_mandatory",
        target_field=field_name,
    )


@_register_pattern(
    r"make\s+['\"](.+?)['\"]\s+optional|['\"](.+?)['\"]\s+should\s+be\s+optional"
)
def _parse_optional(m: re.Match) -> BundleEditCommand:
    field_name = m.group(1) or m.group(2)
    return BundleEditCommand(
        action="make_optional",
        target_field=field_name,
    )


@_register_pattern(
    r"change\s+(?:the\s+)?(?:data\s*)?type\s+(?:of\s+)?['\"](.+?)['\"]\s+to\s+(\w+)"
)
def _parse_change_type(m: re.Match) -> BundleEditCommand:
    data_type = _normalize_data_type(m.group(2)) or m.group(2)
    return BundleEditCommand(
        action="change_type",
        target_field=m.group(1),
        params={"new_type": data_type},
    )


@_register_pattern(
    r"add\s+option[s]?\s+(.+?)\s+to\s+['\"](.+?)['\"]"
)
def _parse_add_option(m: re.Match) -> BundleEditCommand:
    options = _parse_options_list(m.group(1))
    return BundleEditCommand(
        action="add_option",
        target_field=m.group(2),
        params={"options": options},
    )


@_register_pattern(
    r"remove\s+option[s]?\s+(.+?)\s+from\s+['\"](.+?)['\"]"
)
def _parse_remove_option(m: re.Match) -> BundleEditCommand:
    options = _parse_options_list(m.group(1))
    return BundleEditCommand(
        action="remove_option",
        target_field=m.group(2),
        params={"options": options},
    )


def _try_deterministic_parse(instruction: str) -> list[BundleEditCommand] | None:
    """Try to parse instruction using regex patterns. Returns None if no match."""
    instruction = instruction.strip()
    for pattern, handler in _DETERMINISTIC_PATTERNS:
        m = pattern.search(instruction)
        if m:
            cmd = handler(m)
            return [cmd]
    return None


# ---------------------------------------------------------------------------
# LLM-based parser — handles complex / ambiguous instructions
# ---------------------------------------------------------------------------

_LLM_PARSE_SYSTEM_PROMPT = """You parse natural language instructions for editing Avni bundles into structured JSON commands.

Valid actions:
- rename_field: Rename a concept/field. params: {"new_name": "..."}
- add_field: Add a new field. params: {"data_type": "Text|Numeric|Date|Coded|...", "options": [...] (for Coded)}
- remove_field: Remove a field from forms and concepts
- make_mandatory: Make a field mandatory
- make_optional: Make a field optional
- change_type: Change data type. params: {"new_type": "Numeric|Text|Coded|..."}
- add_option: Add options to a Coded field. params: {"options": ["opt1", "opt2"]}
- remove_option: Remove options from a Coded field. params: {"options": ["opt1"]}

Avni data types: Text, Numeric, Date, DateTime, Time, Coded, Notes, Image, Video, Audio, File, PhoneNumber, Location, Duration, Id, NA, Subject

Respond with ONLY a JSON array of command objects:
[{"action": "...", "target_field": "...", "target_form": null, "params": {...}}]

If the instruction mentions a specific form, set target_form. Otherwise null.
If multiple edits are needed, return multiple objects in the array.
ONLY return valid JSON — no markdown, no explanation."""


async def _llm_parse(instruction: str) -> list[BundleEditCommand]:
    """Parse instruction using LLM when deterministic parsing fails."""
    from app.services.claude_client import claude_client

    response = await claude_client.complete(
        messages=[{"role": "user", "content": instruction}],
        system_prompt=_LLM_PARSE_SYSTEM_PROMPT,
    )

    # Extract JSON from response (handle markdown code blocks)
    text = response.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        logger.error("LLM returned invalid JSON for bundle edit parse: %s", text)
        raise ValueError(
            f"Could not parse instruction into edit commands. LLM response: {text[:200]}"
        )

    if not isinstance(parsed, list):
        parsed = [parsed]

    commands = []
    for item in parsed:
        action = item.get("action", "")
        if action not in VALID_ACTIONS:
            logger.warning("LLM returned unknown action '%s', skipping", action)
            continue
        commands.append(
            BundleEditCommand(
                action=action,
                target_field=item.get("target_field", ""),
                target_form=item.get("target_form"),
                params=item.get("params", {}),
            )
        )

    if not commands:
        raise ValueError(f"No valid edit commands parsed from instruction: {instruction}")

    return commands


# ---------------------------------------------------------------------------
# Public parse API
# ---------------------------------------------------------------------------

async def parse_edit_command(instruction: str) -> list[BundleEditCommand]:
    """Parse a natural language instruction into structured edit commands.

    Tries deterministic regex parsing first for speed and reliability.
    Falls back to LLM parsing for complex or ambiguous instructions.
    """
    if not instruction or not instruction.strip():
        raise ValueError("Empty instruction")

    # Try deterministic first
    commands = _try_deterministic_parse(instruction)
    if commands:
        logger.info(
            "Deterministic parse: %s -> %s",
            instruction[:80],
            [c.action for c in commands],
        )
        return commands

    # Fall back to LLM
    logger.info("Falling back to LLM parse for: %s", instruction[:80])
    commands = await _llm_parse(instruction)
    logger.info(
        "LLM parse: %s -> %s",
        instruction[:80],
        [c.action for c in commands],
    )
    return commands


# ---------------------------------------------------------------------------
# Bundle file I/O helpers
# ---------------------------------------------------------------------------

def _bundle_dir(bundle_id: str) -> Path:
    """Get the bundle directory path, validating it exists."""
    path = Path(settings.BUNDLE_OUTPUT_DIR) / bundle_id
    if not path.is_dir():
        raise FileNotFoundError(f"Bundle directory not found: {path}")
    return path


def _read_json(filepath: Path) -> Any:
    """Read and parse a JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(filepath: Path, data: Any) -> None:
    """Write data to a JSON file with consistent formatting."""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _list_form_files(bundle_path: Path) -> list[Path]:
    """List all form JSON files in the bundle."""
    forms_dir = bundle_path / "forms"
    if not forms_dir.is_dir():
        return []
    return sorted(forms_dir.glob("*.json"))


def _find_concept(concepts: list[dict], name: str) -> dict | None:
    """Find a concept by name (case-insensitive)."""
    name_lower = name.lower()
    for c in concepts:
        if c.get("name", "").lower() == name_lower:
            return c
    return None


def _find_form_elements(form_data: dict, field_name: str) -> list[dict]:
    """Find all form elements matching a field name across all groups."""
    field_lower = field_name.lower()
    results = []
    for group in form_data.get("formElementGroups", []):
        for element in group.get("formElements", []):
            concept = element.get("concept", {})
            if concept.get("name", "").lower() == field_lower:
                results.append(element)
            elif element.get("name", "").lower() == field_lower:
                results.append(element)
    return results


# ---------------------------------------------------------------------------
# Edit applicators — one per action type
# ---------------------------------------------------------------------------

def _apply_rename_field(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Rename a field in concepts.json and all form files."""
    old_name = command.target_field
    new_name = command.params.get("new_name", "")
    if not new_name:
        raise ValueError("rename_field requires 'new_name' param")

    changes: list[str] = []

    # Update concepts.json
    concepts_path = bundle_path / "concepts.json"
    if concepts_path.is_file():
        concepts = _read_json(concepts_path)
        concept = _find_concept(concepts, old_name)
        if concept:
            concept["name"] = new_name
            # Also update answers in other concepts that reference this name
            for c in concepts:
                for answer in c.get("answers", []):
                    if answer.get("name", "").lower() == old_name.lower():
                        answer["name"] = new_name
            _write_json(concepts_path, concepts)
            changes.append(f"concepts.json: renamed concept '{old_name}' -> '{new_name}'")
        else:
            return {
                "success": False,
                "error": f"Concept '{old_name}' not found in concepts.json",
                "changes": [],
            }

    # Update form files
    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        modified = False
        for group in form_data.get("formElementGroups", []):
            for element in group.get("formElements", []):
                concept = element.get("concept", {})
                if concept.get("name", "").lower() == old_name.lower():
                    concept["name"] = new_name
                    element["name"] = new_name
                    # Update answer names within the concept
                    for answer in concept.get("answers", []):
                        if answer.get("name", "").lower() == old_name.lower():
                            answer["name"] = new_name
                    modified = True
        if modified:
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: renamed element '{old_name}' -> '{new_name}'"
            )

    return {"success": True, "changes": changes}


def _apply_add_field(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Add a new field to concepts.json and optionally to form files."""
    field_name = command.target_field
    data_type = command.params.get("data_type", "Text")
    options = command.params.get("options", [])
    changes: list[str] = []

    # Generate a UUID for the new concept
    concept_uuid = str(uuid.uuid4())

    # Build the concept
    new_concept: dict[str, Any] = {
        "name": field_name,
        "uuid": concept_uuid,
        "dataType": data_type,
        "active": True,
    }

    answer_concepts: list[dict[str, Any]] = []
    if data_type == "Coded" and options:
        new_concept["answers"] = []
        for i, opt_name in enumerate(options):
            opt_uuid = str(uuid.uuid4())
            new_concept["answers"].append({
                "name": opt_name,
                "uuid": opt_uuid,
                "order": float(i),
            })
            answer_concepts.append({
                "name": opt_name,
                "uuid": opt_uuid,
                "dataType": "NA",
                "active": True,
            })

    # Add to concepts.json
    concepts_path = bundle_path / "concepts.json"
    if concepts_path.is_file():
        concepts = _read_json(concepts_path)
        # Check for duplicates
        if _find_concept(concepts, field_name):
            return {
                "success": False,
                "error": f"Concept '{field_name}' already exists in concepts.json",
                "changes": [],
            }
        concepts.append(new_concept)
        # Add answer concepts (NA type) if they don't already exist
        for ac in answer_concepts:
            if not _find_concept(concepts, ac["name"]):
                concepts.append(ac)
        _write_json(concepts_path, concepts)
        changes.append(
            f"concepts.json: added concept '{field_name}' ({data_type})"
        )
        if options:
            changes.append(
                f"concepts.json: added {len(options)} answer option(s): {', '.join(options)}"
            )
    else:
        return {
            "success": False,
            "error": "concepts.json not found in bundle",
            "changes": [],
        }

    # Add to form files if target_form is specified
    if command.target_form:
        form_files = [
            f for f in _list_form_files(bundle_path)
            if f.stem.lower() == command.target_form.lower()
        ]
        for form_path in form_files:
            form_data = _read_json(form_path)
            groups = form_data.get("formElementGroups", [])
            if not groups:
                continue

            # Add to the last group
            target_group = groups[-1]
            existing_elements = target_group.get("formElements", [])

            # Build form element concept
            form_concept: dict[str, Any] = {
                "name": field_name,
                "uuid": concept_uuid,
                "dataType": data_type,
                "answers": [],
                "active": True,
                "media": [],
            }
            if data_type == "Coded" and new_concept.get("answers"):
                form_concept["answers"] = [
                    {
                        "name": a["name"],
                        "uuid": a["uuid"],
                        "dataType": "NA",
                        "answers": [],
                        "order": a["order"],
                        "active": True,
                        "media": [],
                    }
                    for a in new_concept["answers"]
                ]

            element_type = "SingleSelect" if data_type == "Coded" else data_type
            display_order = max(
                (e.get("displayOrder", 0) for e in existing_elements),
                default=0,
            ) + 1.0

            new_element = {
                "name": field_name,
                "uuid": str(uuid.uuid4()),
                "keyValues": [],
                "concept": form_concept,
                "displayOrder": display_order,
                "type": element_type,
                "mandatory": False,
                "voided": False,
            }
            existing_elements.append(new_element)
            target_group["formElements"] = existing_elements
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: added element '{field_name}' to group '{target_group.get('name', '?')}'"
            )

    return {"success": True, "changes": changes}


def _apply_remove_field(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Remove a field from forms and concepts."""
    field_name = command.target_field
    changes: list[str] = []

    # Remove from form files first
    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        modified = False
        for group in form_data.get("formElementGroups", []):
            original_count = len(group.get("formElements", []))
            group["formElements"] = [
                el for el in group.get("formElements", [])
                if el.get("concept", {}).get("name", "").lower() != field_name.lower()
                and el.get("name", "").lower() != field_name.lower()
            ]
            if len(group["formElements"]) < original_count:
                modified = True
                # Re-number display orders
                for i, el in enumerate(group["formElements"]):
                    el["displayOrder"] = float(i + 1)
        if modified:
            _write_json(form_path, form_data)
            changes.append(f"forms/{form_path.name}: removed element '{field_name}'")

    # Remove from concepts.json (only if not used in other forms)
    concepts_path = bundle_path / "concepts.json"
    if concepts_path.is_file():
        concepts = _read_json(concepts_path)
        concept = _find_concept(concepts, field_name)
        if concept:
            # Collect answer UUIDs to remove their NA concepts too
            answer_names = [a["name"] for a in concept.get("answers", [])]

            concepts = [
                c for c in concepts
                if c.get("name", "").lower() != field_name.lower()
            ]
            # Remove orphaned answer concepts (NA type only)
            if answer_names:
                # Check if any answer is still used by another concept
                remaining_answer_refs = set()
                for c in concepts:
                    for a in c.get("answers", []):
                        remaining_answer_refs.add(a.get("name", "").lower())

                for a_name in answer_names:
                    if a_name.lower() not in remaining_answer_refs:
                        concepts = [
                            c for c in concepts
                            if not (
                                c.get("name", "").lower() == a_name.lower()
                                and c.get("dataType") == "NA"
                            )
                        ]

            _write_json(concepts_path, concepts)
            changes.append(f"concepts.json: removed concept '{field_name}'")
    if not changes:
        return {
            "success": False,
            "error": f"Field '{field_name}' not found in any bundle file",
            "changes": [],
        }

    return {"success": True, "changes": changes}


def _apply_make_mandatory(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Set a field as mandatory in form files."""
    return _set_mandatory(bundle_path, command, mandatory=True)


def _apply_make_optional(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Set a field as optional in form files."""
    return _set_mandatory(bundle_path, command, mandatory=False)


def _set_mandatory(
    bundle_path: Path, command: BundleEditCommand, *, mandatory: bool,
) -> dict[str, Any]:
    """Set mandatory flag on a field across form files."""
    field_name = command.target_field
    changes: list[str] = []
    label = "mandatory" if mandatory else "optional"

    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        elements = _find_form_elements(form_data, field_name)
        if elements:
            for el in elements:
                el["mandatory"] = mandatory
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: set '{field_name}' to {label}"
            )

    if not changes:
        return {
            "success": False,
            "error": f"Field '{field_name}' not found in any form",
            "changes": [],
        }

    return {"success": True, "changes": changes}


def _apply_change_type(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Change the data type of a concept and update form elements."""
    field_name = command.target_field
    new_type = command.params.get("new_type", "")
    if not new_type:
        raise ValueError("change_type requires 'new_type' param")

    changes: list[str] = []

    # Update concepts.json
    concepts_path = bundle_path / "concepts.json"
    if concepts_path.is_file():
        concepts = _read_json(concepts_path)
        concept = _find_concept(concepts, field_name)
        if concept:
            old_type = concept.get("dataType", "?")
            concept["dataType"] = new_type
            # Clear answers if changing away from Coded
            if old_type == "Coded" and new_type != "Coded":
                concept.pop("answers", None)
            # Add empty answers array if changing to Coded
            if new_type == "Coded" and "answers" not in concept:
                concept["answers"] = []
            _write_json(concepts_path, concepts)
            changes.append(
                f"concepts.json: changed '{field_name}' from {old_type} to {new_type}"
            )
        else:
            return {
                "success": False,
                "error": f"Concept '{field_name}' not found in concepts.json",
                "changes": [],
            }

    # Update form elements
    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        elements = _find_form_elements(form_data, field_name)
        if elements:
            for el in elements:
                concept = el.get("concept", {})
                concept["dataType"] = new_type
                if new_type == "Coded":
                    el["type"] = "SingleSelect"
                    if "answers" not in concept:
                        concept["answers"] = []
                else:
                    el["type"] = new_type
                    concept.pop("answers", None)
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: updated element type for '{field_name}'"
            )

    return {"success": True, "changes": changes}


def _apply_add_option(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Add options to a Coded concept."""
    field_name = command.target_field
    new_options = command.params.get("options", [])
    if not new_options:
        raise ValueError("add_option requires 'options' param")

    changes: list[str] = []

    concepts_path = bundle_path / "concepts.json"
    if not concepts_path.is_file():
        return {"success": False, "error": "concepts.json not found", "changes": []}

    concepts = _read_json(concepts_path)
    concept = _find_concept(concepts, field_name)
    if not concept:
        return {
            "success": False,
            "error": f"Concept '{field_name}' not found in concepts.json",
            "changes": [],
        }

    if concept.get("dataType") != "Coded":
        return {
            "success": False,
            "error": f"Concept '{field_name}' is {concept.get('dataType')}, not Coded. Cannot add options.",
            "changes": [],
        }

    existing_answers = concept.get("answers", [])
    existing_names = {a.get("name", "").lower() for a in existing_answers}
    added = []

    for opt_name in new_options:
        if opt_name.lower() in existing_names:
            continue
        opt_uuid = str(uuid.uuid4())
        existing_answers.append({
            "name": opt_name,
            "uuid": opt_uuid,
            "order": float(len(existing_answers)),
        })
        # Add NA concept for the answer if not present
        if not _find_concept(concepts, opt_name):
            concepts.append({
                "name": opt_name,
                "uuid": opt_uuid,
                "dataType": "NA",
                "active": True,
            })
        added.append(opt_name)

    concept["answers"] = existing_answers
    _write_json(concepts_path, concepts)
    if added:
        changes.append(
            f"concepts.json: added option(s) {added} to '{field_name}'"
        )

    # Update form elements
    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        elements = _find_form_elements(form_data, field_name)
        if elements:
            for el in elements:
                el_concept = el.get("concept", {})
                el_answers = el_concept.get("answers", [])
                el_existing_names = {a.get("name", "").lower() for a in el_answers}
                for a in concept["answers"]:
                    if a["name"].lower() not in el_existing_names:
                        el_answers.append({
                            "name": a["name"],
                            "uuid": a["uuid"],
                            "dataType": "NA",
                            "answers": [],
                            "order": a["order"],
                            "active": True,
                            "media": [],
                        })
                el_concept["answers"] = el_answers
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: updated options for '{field_name}'"
            )

    if not changes:
        return {
            "success": True,
            "changes": [f"No new options to add (all already exist on '{field_name}')"],
        }

    return {"success": True, "changes": changes}


def _apply_remove_option(
    bundle_path: Path, command: BundleEditCommand,
) -> dict[str, Any]:
    """Remove options from a Coded concept."""
    field_name = command.target_field
    options_to_remove = command.params.get("options", [])
    if not options_to_remove:
        raise ValueError("remove_option requires 'options' param")

    changes: list[str] = []
    remove_lower = {o.lower() for o in options_to_remove}

    concepts_path = bundle_path / "concepts.json"
    if not concepts_path.is_file():
        return {"success": False, "error": "concepts.json not found", "changes": []}

    concepts = _read_json(concepts_path)
    concept = _find_concept(concepts, field_name)
    if not concept:
        return {
            "success": False,
            "error": f"Concept '{field_name}' not found",
            "changes": [],
        }

    if concept.get("dataType") != "Coded":
        return {
            "success": False,
            "error": f"Concept '{field_name}' is not Coded",
            "changes": [],
        }

    original_count = len(concept.get("answers", []))
    concept["answers"] = [
        a for a in concept.get("answers", [])
        if a.get("name", "").lower() not in remove_lower
    ]
    # Reorder
    for i, a in enumerate(concept["answers"]):
        a["order"] = float(i)

    removed_count = original_count - len(concept["answers"])
    if removed_count > 0:
        # Remove orphaned NA concepts
        remaining_refs = set()
        for c in concepts:
            for a in c.get("answers", []):
                remaining_refs.add(a.get("name", "").lower())

        for opt_name in options_to_remove:
            if opt_name.lower() not in remaining_refs:
                concepts = [
                    c for c in concepts
                    if not (
                        c.get("name", "").lower() == opt_name.lower()
                        and c.get("dataType") == "NA"
                    )
                ]

        _write_json(concepts_path, concepts)
        changes.append(
            f"concepts.json: removed {removed_count} option(s) from '{field_name}'"
        )

    # Update form elements
    form_files = _list_form_files(bundle_path)
    if command.target_form:
        form_files = [
            f for f in form_files
            if f.stem.lower() == command.target_form.lower()
        ]

    for form_path in form_files:
        form_data = _read_json(form_path)
        elements = _find_form_elements(form_data, field_name)
        if elements:
            for el in elements:
                el_concept = el.get("concept", {})
                el_concept["answers"] = [
                    a for a in el_concept.get("answers", [])
                    if a.get("name", "").lower() not in remove_lower
                ]
                for i, a in enumerate(el_concept["answers"]):
                    a["order"] = float(i)
            _write_json(form_path, form_data)
            changes.append(
                f"forms/{form_path.name}: removed option(s) from '{field_name}'"
            )

    if not changes:
        return {
            "success": False,
            "error": f"Options {options_to_remove} not found on '{field_name}'",
            "changes": [],
        }

    return {"success": True, "changes": changes}


# Action dispatch table
_ACTION_HANDLERS: dict[str, callable] = {
    "rename_field": _apply_rename_field,
    "add_field": _apply_add_field,
    "remove_field": _apply_remove_field,
    "make_mandatory": _apply_make_mandatory,
    "make_optional": _apply_make_optional,
    "change_type": _apply_change_type,
    "add_option": _apply_add_option,
    "remove_option": _apply_remove_option,
}


# ---------------------------------------------------------------------------
# Public apply API
# ---------------------------------------------------------------------------

def apply_edit(bundle_id: str, command: BundleEditCommand) -> dict[str, Any]:
    """Apply a single edit command to a bundle's files on disk.

    Returns:
        {"success": bool, "changes": list[str], "error": str | None}
    """
    if command.action not in _ACTION_HANDLERS:
        return {
            "success": False,
            "error": f"Unknown action: {command.action}",
            "changes": [],
        }

    try:
        bundle_path = _bundle_dir(bundle_id)
    except FileNotFoundError as e:
        return {"success": False, "error": str(e), "changes": []}

    handler = _ACTION_HANDLERS[command.action]
    try:
        return handler(bundle_path, command)
    except Exception as e:
        logger.exception(
            "Error applying %s to bundle %s", command.action, bundle_id
        )
        return {"success": False, "error": str(e), "changes": []}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def edit_bundle_nl(bundle_id: str, instruction: str) -> dict[str, Any]:
    """Parse a natural language instruction and apply edits to a bundle.

    This is the main entry point for the bundle editor service.

    Args:
        bundle_id: The bundle ID (directory under BUNDLE_OUTPUT_DIR)
        instruction: Natural language edit instruction

    Returns:
        {
            "success": bool,
            "bundle_id": str,
            "instruction": str,
            "commands": [{"action": ..., "description": ...}],
            "changes": [str],
            "errors": [str],
        }
    """
    # Validate bundle exists
    try:
        _bundle_dir(bundle_id)
    except FileNotFoundError:
        return {
            "success": False,
            "bundle_id": bundle_id,
            "instruction": instruction,
            "commands": [],
            "changes": [],
            "errors": [f"Bundle '{bundle_id}' not found"],
        }

    # Parse instruction
    try:
        commands = await parse_edit_command(instruction)
    except ValueError as e:
        return {
            "success": False,
            "bundle_id": bundle_id,
            "instruction": instruction,
            "commands": [],
            "changes": [],
            "errors": [str(e)],
        }

    # Apply each command
    all_changes: list[str] = []
    all_errors: list[str] = []

    for cmd in commands:
        result = apply_edit(bundle_id, cmd)
        all_changes.extend(result.get("changes", []))
        if not result.get("success"):
            error = result.get("error", "Unknown error")
            all_errors.append(f"{cmd.describe()}: {error}")

    overall_success = len(all_errors) == 0 and len(all_changes) > 0

    return {
        "success": overall_success,
        "bundle_id": bundle_id,
        "instruction": instruction,
        "commands": [
            {"action": cmd.action, "description": cmd.describe()}
            for cmd in commands
        ],
        "changes": all_changes,
        "errors": all_errors,
    }
