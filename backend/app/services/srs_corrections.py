"""Deterministic SRS correction engine — replaces LLM-based SRSData mutation.

Instead of sending the entire SRSData JSON to an LLM for correction (which
hallucinates, drops forms, invents programs), this module:
1. Uses a small LLM call to classify the user's message into a structured command
2. Applies the command deterministically to SRSData — no LLM touches the data

Covers 90%+ of real corrections users make during the review step.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from pydantic import BaseModel

from app.models.schemas import SRSData, SRSFormDefinition
from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command model
# ---------------------------------------------------------------------------

class CorrectionCommand(BaseModel):
    """Structured correction command — what to do, not how to do it."""
    command: str       # move_to_program, move_to_encounter, change_form_type, etc.
    entity: str        # The entity being changed (name)
    target: str = ""   # Target context (e.g., program name for move_to_encounter)
    value: str = ""    # New value (e.g., new name for rename)


CLASSIFY_PROMPT_TEMPLATE = """You are a command classifier for the Avni AI platform. The user wants to correct parsed SRS data.

Classify the user's message into EXACTLY one JSON command:

{{"command": "<one of the commands below>", "entity": "<entity name>", "target": "<target if needed>", "value": "<new value if needed>"}}

Commands:
- "move_to_program": User says X should be a program (not encounter type). entity=X
- "move_to_encounter": User says X should be an encounter under program Y. entity=X, target=Y
- "change_form_type": User says form X should be type Y. entity=X, value=Y (IndividualProfile/ProgramEnrolment/ProgramEncounter/Encounter)
- "remove_form": User says remove/delete form X. entity=X
- "rename": User says rename X to Y. entity=X, value=Y
- "change_data_type": User says field X should be Coded/Numeric/Text/etc. entity=X, value=new_type
- "set_mandatory": User says make field X mandatory or optional. entity=X, value=Yes or No
- "add_field": User says add field X to form Y. entity=X, target=Y, value=data_type
- "set_subject_type": User says X is a subject type. entity=X
- "unknown": Can't classify. entity=user's full message

Current SRS has:
- Subject Types: {subject_types}
- Programs: {programs}
- Encounter Types: {encounter_types}
- Forms: {forms}

Respond with JSON only, no explanation."""


async def classify_correction(message: str, srs: SRSData) -> CorrectionCommand:
    """Use LLM to classify the user's correction into a structured command.

    The LLM returns ONLY the command type + params. It never sees or modifies
    the actual SRSData — that's done deterministically by apply_correction().
    """
    programs = [p.get("name", p) if isinstance(p, dict) else str(p) for p in srs.programs]
    sts = [st.get("name", "") if isinstance(st, dict) else str(st) for st in srs.subjectTypes]
    forms = [f.name for f in srs.forms]

    prompt = CLASSIFY_PROMPT_TEMPLATE.format(
        subject_types=sts,
        programs=programs,
        encounter_types=srs.encounterTypes,
        forms=forms,
    )

    try:
        response = await claude_client.complete(
            messages=[{"role": "user", "content": message}],
            system_prompt=prompt,
            task_type="intent",
        )

        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        return CorrectionCommand(**data)

    except Exception as e:
        logger.warning("Correction classification failed: %s", e)
        return CorrectionCommand(command="unknown", entity=message)


# ---------------------------------------------------------------------------
# Deterministic command executors
# ---------------------------------------------------------------------------

def apply_correction(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Apply a correction command deterministically to SRSData.

    Returns (new_srs_data, human_readable_description_of_what_changed).
    No LLM involved — pure data manipulation.
    """
    # Deep copy to avoid mutating the original
    srs = srs.model_copy(deep=True)

    handler = _HANDLERS.get(cmd.command)
    if handler:
        return handler(srs, cmd)

    return srs, f"Unknown command: {cmd.command}. Please describe the change differently."


def _move_to_program(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Move an entity to programs. Handles both entity names and form names."""
    raw_name = cmd.entity
    # Extract a clean program name:
    # User might say entity="Form 2 - Institution Enrollment" when they mean program="Institution"
    # Also handle: "Institution", "Form 2 - Institution", etc.
    # Use cmd.value as the clean name if provided, otherwise extract from entity
    if cmd.value:
        program_name = cmd.value
    else:
        program_name = raw_name
        # Strip common prefixes: "Form N - ", "Form N. "
        import re as _re
        cleaned = _re.sub(r'^Form\s*\d+\s*[-:.]\s*', '', program_name, flags=_re.IGNORECASE)
        # Strip common suffixes: " Enrollment", " Enrolment", " Registration"
        cleaned = _re.sub(r'\s*(Enroll?ment|Registration|Exit|Cancellation)\s*$', '', cleaned, flags=_re.IGNORECASE)
        if cleaned.strip():
            program_name = cleaned.strip()

    # Remove from encounter types (match both raw name and clean name)
    srs.encounterTypes = [
        et for et in srs.encounterTypes
        if et != raw_name and et != program_name
    ]

    # Add to programs if not already there
    program_names = {p.get("name", p) if isinstance(p, dict) else str(p) for p in srs.programs}
    if program_name not in program_names:
        srs.programs.append({"name": program_name, "colour": "#4CAF50"})
    # Remove old program name if it was the raw form name
    if raw_name != program_name and raw_name in program_names:
        srs.programs = [
            p for p in srs.programs
            if (p.get("name", p) if isinstance(p, dict) else str(p)) != raw_name
        ]

    # Collect all old names that should map to the new program name
    # (heuristic parser may have used sheet names like "Form 2 - Institution")
    old_names = {raw_name, program_name}
    # Also match any existing programName that contains the clean program name
    for form in srs.forms:
        if form.programName and program_name.lower() in form.programName.lower():
            old_names.add(form.programName)

    # Update ALL forms that reference any old name variant
    for form in srs.forms:
        name_lower = form.name.lower()
        prog_lower = program_name.lower()

        # Enrolment form detection
        if ("enrol" in name_lower and prog_lower in name_lower):
            form.formType = "ProgramEnrolment"
            form.programName = program_name
            form.encounterTypeName = None

        # Any form whose programName matches any old variant → update to clean name
        elif form.programName and form.programName in old_names:
            form.programName = program_name

        # Encounter types that reference old names
        elif form.encounterTypeName and form.encounterTypeName in old_names:
            form.encounterTypeName = None
            form.formType = "ProgramEnrolment"
            form.programName = program_name

    # Also update programEncounterMappings
    if srs.programEncounterMappings:
        for m in srs.programEncounterMappings:
            if m.get("program") in old_names:
                m["program"] = program_name

    # Clean up: remove old program names from programs list
    for old in old_names:
        if old != program_name:
            srs.programs = [
                p for p in srs.programs
                if (p.get("name", p) if isinstance(p, dict) else str(p)) != old
            ]

    return srs, f"Added **{program_name}** as a program. Updated all form references."


def _move_to_encounter(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Move an entity to encounter types under a specific program."""
    name = cmd.entity
    program = cmd.target

    # Remove from programs if it was there
    srs.programs = [p for p in srs.programs
                    if (p.get("name", p) if isinstance(p, dict) else str(p)) != name]

    # Add to encounter types
    if name not in srs.encounterTypes:
        srs.encounterTypes.append(name)

    # Update forms
    for form in srs.forms:
        if form.programName == name and form.formType == "ProgramEnrolment":
            form.formType = "ProgramEncounter"
            form.encounterTypeName = name
            form.programName = program
        elif name.lower() in form.name.lower():
            if form.formType in ("IndividualProfile", "ProgramEnrolment"):
                form.formType = "ProgramEncounter"
            form.encounterTypeName = name
            if program:
                form.programName = program

    # Update programEncounterMappings
    if program:
        if not srs.programEncounterMappings:
            srs.programEncounterMappings = []
        found = False
        for m in srs.programEncounterMappings:
            if m.get("program") == program:
                if name not in m.get("encounterTypes", []):
                    m.setdefault("encounterTypes", []).append(name)
                found = True
        if not found:
            srs.programEncounterMappings.append({"program": program, "encounterTypes": [name]})

    return srs, f"Moved **{name}** to encounter types under program **{program}**."


def _change_form_type(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Change a form's formType."""
    for form in srs.forms:
        if form.name.lower() == cmd.entity.lower() or cmd.entity.lower() in form.name.lower():
            old_type = form.formType
            form.formType = cmd.value
            return srs, f"Changed **{form.name}** from {old_type} to {cmd.value}."
    return srs, f"Form '{cmd.entity}' not found."


def _remove_form(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Remove a form from SRS."""
    original_count = len(srs.forms)
    srs.forms = [f for f in srs.forms if f.name.lower() != cmd.entity.lower()
                 and cmd.entity.lower() not in f.name.lower()]
    removed = original_count - len(srs.forms)
    if removed:
        return srs, f"Removed {removed} form(s) matching '{cmd.entity}'."
    return srs, f"No form matching '{cmd.entity}' found."


def _rename(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Rename an entity across all references."""
    old_name = cmd.entity
    new_name = cmd.value

    # Rename in programs
    for p in srs.programs:
        if isinstance(p, dict) and p.get("name") == old_name:
            p["name"] = new_name

    # Rename in encounter types
    srs.encounterTypes = [new_name if et == old_name else et for et in srs.encounterTypes]

    # Rename in subject types
    for st in srs.subjectTypes:
        if isinstance(st, dict) and st.get("name") == old_name:
            st["name"] = new_name

    # Rename in forms
    for form in srs.forms:
        if form.name == old_name:
            form.name = new_name
        if form.programName == old_name:
            form.programName = new_name
        if form.encounterTypeName == old_name:
            form.encounterTypeName = new_name

    # Rename in programEncounterMappings
    if srs.programEncounterMappings:
        for m in srs.programEncounterMappings:
            if m.get("program") == old_name:
                m["program"] = new_name
            m["encounterTypes"] = [new_name if et == old_name else et for et in m.get("encounterTypes", [])]

    return srs, f"Renamed **{old_name}** to **{new_name}** across all references."


def _set_subject_type(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Add entity as a subject type."""
    name = cmd.entity
    existing = {st.get("name", "") if isinstance(st, dict) else str(st) for st in srs.subjectTypes}
    if name not in existing:
        srs.subjectTypes.append({"name": name, "type": "Person"})

    # Update any matching form to IndividualProfile
    for form in srs.forms:
        if name.lower() in form.name.lower() and "registr" in form.name.lower():
            form.formType = "IndividualProfile"
            form.subjectTypeName = name

    return srs, f"Added **{name}** as a subject type (Person)."


def _change_data_type(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Change a field's data type across all forms."""
    field_name = cmd.entity
    new_type = cmd.value
    changed = 0
    for form in srs.forms:
        for group in form.groups:
            for field in group.fields:
                if field.name.lower() == field_name.lower():
                    field.dataType = new_type
                    changed += 1
    if changed:
        return srs, f"Changed **{field_name}** data type to **{new_type}** in {changed} form(s)."
    return srs, f"Field '{field_name}' not found in any form."


def _set_mandatory(srs: SRSData, cmd: CorrectionCommand) -> tuple[SRSData, str]:
    """Set field mandatory/optional."""
    field_name = cmd.entity
    mandatory = cmd.value.lower() in ("yes", "true", "mandatory", "required")
    changed = 0
    for form in srs.forms:
        for group in form.groups:
            for field in group.fields:
                if field.name.lower() == field_name.lower():
                    field.mandatory = mandatory
                    changed += 1
    label = "mandatory" if mandatory else "optional"
    if changed:
        return srs, f"Set **{field_name}** to **{label}** in {changed} form(s)."
    return srs, f"Field '{field_name}' not found."


# Command → handler mapping
_HANDLERS = {
    "move_to_program": _move_to_program,
    "move_to_encounter": _move_to_encounter,
    "change_form_type": _change_form_type,
    "remove_form": _remove_form,
    "rename": _rename,
    "set_subject_type": _set_subject_type,
    "change_data_type": _change_data_type,
    "set_mandatory": _set_mandatory,
}
