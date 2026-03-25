"""Sector-aware form classifier.

Uses production patterns from 13+ Avni orgs to correctly classify forms
based on the org's sector (MCH, Education, Community Development, etc.).

Loaded from sector_patterns.json — extracted from Avni production read DB.
"""

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_PATTERNS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "knowledge", "data", "sector_patterns.json"
)

_patterns: dict | None = None


def _load_patterns() -> dict:
    global _patterns
    if _patterns is None:
        with open(_PATTERNS_FILE) as f:
            _patterns = json.load(f)
    return _patterns


def get_sector_names() -> list[str]:
    """Return available sector names."""
    return list(_load_patterns()["sectors"].keys())


def get_sector_info(sector: str) -> dict | None:
    """Get sector configuration."""
    patterns = _load_patterns()
    # Fuzzy match sector name
    sector_lower = sector.lower().strip()
    for key, val in patterns["sectors"].items():
        if key.lower() == sector_lower:
            return val
        # Check aliases in description
        if sector_lower in val.get("description", "").lower():
            return val
    return None


def classify_forms_by_sector(
    forms: list[Any],
    subject_types: list[dict],
    programs: list[dict],
    program_encounters_meta: list[dict],
    encounters_meta: list[dict],
    sector: str | None = None,
) -> None:
    """Classify forms using sector-specific rules from production data.

    Modifies forms in-place: sets formType, programName, encounterTypeName, subjectTypeName.

    Args:
        forms: List of SRSFormDefinition objects
        subject_types: Parsed subject types [{"name": "Child", "type": "Person"}, ...]
        programs: Parsed programs [{"name": "Sapno Ki Udaan"}, ...]
        program_encounters_meta: From modelling doc [{"encounter_name": ..., "program_name": ..., "subject_type": ...}]
        encounters_meta: From modelling doc [{"name": ..., "subject_type": ...}]
        sector: Optional sector hint (MCH, Education, etc.)
    """
    patterns = _load_patterns()
    sector_info = get_sector_info(sector) if sector else None

    # Build lookup maps
    st_names = {st["name"].lower(): st["name"] for st in subject_types}
    st_types = {st["name"].lower(): st.get("type", "Person") for st in subject_types}
    prog_names = {p["name"].lower() if isinstance(p, dict) else p.lower():
                  p["name"] if isinstance(p, dict) else p for p in programs}

    # Build encounter → program mapping from program_encounters_meta
    enc_to_program: dict[str, str] = {}
    enc_to_subject: dict[str, str] = {}
    for pe in program_encounters_meta:
        enc_name = pe.get("encounter_name", "").strip()
        prog = pe.get("program_name", "").strip()
        subj = pe.get("subject_type", "").strip()
        if enc_name:
            if prog and prog.lower() in prog_names:
                enc_to_program[enc_name.lower()] = prog_names[prog.lower()]
            elif prog:
                # program_name might actually be subject_type (column misread)
                # Check if it's a known subject type
                if prog.lower() in st_names:
                    enc_to_subject[enc_name.lower()] = st_names[prog.lower()]
                    # Try to find the actual program for this encounter
                    _infer_program_for_encounter(enc_name, prog_names, enc_to_program)
            if subj and subj.lower() in st_names:
                enc_to_subject[enc_name.lower()] = st_names[subj.lower()]

    # Build standalone encounter → subject type from encounters_meta
    for em in encounters_meta:
        enc_name = em.get("name", "").strip()
        subj = em.get("subject_type", "").strip()
        if enc_name and subj and subj.lower() in st_names:
            enc_to_subject[enc_name.lower()] = st_names[subj.lower()]

    # Classify each form
    for form in forms:
        if form.formType and form.formType != "Encounter":
            # Already classified (registration, enrolment, exit)
            _assign_subject_type_if_missing(form, st_names, enc_to_subject, sector_info)
            continue

        name_lower = form.name.strip().lower()

        # Skip if already has correct classification
        if form.formType == "ProgramEncounter" and form.programName:
            _assign_subject_type_if_missing(form, st_names, enc_to_subject, sector_info)
            continue

        # 1. Check program encounters meta
        if name_lower in enc_to_program:
            form.formType = "ProgramEncounter"
            form.programName = enc_to_program[name_lower]
            form.encounterTypeName = form.name.strip()
            _assign_subject_type_if_missing(form, st_names, enc_to_subject, sector_info)
            logger.info("Sector classified '%s' → ProgramEncounter (program=%s)", form.name, form.programName)
            continue

        # 2. Check if form name contains a program name (e.g., "Sapno Ki Udaan Exit form")
        matched_prog = _match_program_in_name(name_lower, prog_names)
        if matched_prog:
            if "exit" in name_lower:
                form.formType = "ProgramExit"
                form.programName = matched_prog
                logger.info("Sector classified '%s' → ProgramExit (program=%s)", form.name, matched_prog)
                continue
            elif "enrol" in name_lower:
                form.formType = "ProgramEnrolment"
                form.programName = matched_prog
                continue

        # 3. Use sector-specific rules
        if sector_info:
            classified = _classify_by_sector_rules(form, name_lower, sector_info, st_names, prog_names, enc_to_subject)
            if classified:
                continue

        # 4. Use encounter metadata subject type
        if name_lower in enc_to_subject:
            subj = enc_to_subject[name_lower]
            form.subjectTypeName = subj
            # If subject type is a Group/Individual (not Person), it's a standalone Encounter
            if st_types.get(subj.lower()) in ("Group", "Individual", "Household"):
                form.formType = "Encounter"
                form.encounterTypeName = form.name.strip()
                logger.info("Sector classified '%s' → Encounter on %s", form.name, subj)
                continue

        # 5. If there's only one program and form is unclassified Encounter, check if it should be ProgramEncounter
        if len(programs) == 1 and form.formType == "Encounter":
            only_prog = programs[0]["name"] if isinstance(programs[0], dict) else programs[0]
            # Don't auto-assign if it's clearly a standalone encounter (attendance, meeting, etc.)
            if not _is_standalone_encounter(name_lower):
                form.formType = "ProgramEncounter"
                form.programName = only_prog
                form.encounterTypeName = form.name.strip()
                logger.info("Sector classified '%s' → ProgramEncounter (only program=%s)", form.name, only_prog)
                continue

        # Assign subject type even for unclassified forms
        _assign_subject_type_if_missing(form, st_names, enc_to_subject, sector_info)


def _infer_program_for_encounter(enc_name: str, prog_names: dict, enc_to_program: dict) -> None:
    """Try to infer which program an encounter belongs to by name matching."""
    enc_lower = enc_name.lower()
    for prog_lower, prog_name in prog_names.items():
        if prog_lower in enc_lower or enc_lower in prog_lower:
            enc_to_program[enc_lower] = prog_name
            return


def _match_program_in_name(name_lower: str, prog_names: dict) -> str | None:
    """Check if form name contains a program name."""
    for prog_lower, prog_name in prog_names.items():
        if prog_lower in name_lower:
            return prog_name
    return None


def _is_standalone_encounter(name_lower: str) -> bool:
    """Check if a form name suggests a standalone encounter (not program-linked)."""
    standalone_keywords = [
        "attendance", "meeting", "inspection", "checklist", "survey",
        "assessment", "profile", "registration", "village level",
        "panchayat", "block", "district", "manch", "gram sabha",
    ]
    return any(kw in name_lower for kw in standalone_keywords)


def _classify_by_sector_rules(
    form: Any, name_lower: str, sector_info: dict,
    st_names: dict, prog_names: dict, enc_to_subject: dict,
) -> bool:
    """Apply sector-specific classification rules. Returns True if classified."""

    # Check common_encounters_standalone
    for enc in sector_info.get("common_encounters_standalone", []):
        if isinstance(enc, dict):
            enc_name = enc.get("name", "").lower()
            enc_subject = enc.get("on_subject", "")
            if enc_name and enc_name in name_lower:
                form.formType = "Encounter"
                form.encounterTypeName = form.name.strip()
                if enc_subject and enc_subject.lower() in st_names:
                    form.subjectTypeName = st_names[enc_subject.lower()]
                logger.info("Sector rule classified '%s' → Encounter on %s", form.name, enc_subject)
                return True
        elif isinstance(enc, str) and enc.lower() in name_lower:
            form.formType = "Encounter"
            form.encounterTypeName = form.name.strip()
            return True

    # Check common_programs encounters
    for prog in sector_info.get("common_programs", []):
        prog_name = prog.get("name", "")
        for enc_name in prog.get("encounters", []):
            if enc_name.lower() in name_lower:
                form.formType = "ProgramEncounter"
                form.programName = _find_closest_program(prog_name, prog.get("aliases", []), prog_names)
                form.encounterTypeName = form.name.strip()
                target = prog.get("target_subject", "")
                if target and target.lower() in st_names:
                    form.subjectTypeName = st_names[target.lower()]
                logger.info("Sector rule classified '%s' → ProgramEncounter (program=%s)", form.name, form.programName)
                return True

    return False


def _find_closest_program(preferred_name: str, aliases: list[str], prog_names: dict) -> str | None:
    """Find the closest matching program from available programs."""
    # Exact match
    if preferred_name.lower() in prog_names:
        return prog_names[preferred_name.lower()]
    # Alias match
    for alias in aliases:
        if alias.lower() in prog_names:
            return prog_names[alias.lower()]
    # Substring match
    for prog_lower, prog_name in prog_names.items():
        if preferred_name.lower() in prog_lower or prog_lower in preferred_name.lower():
            return prog_name
    # Return first program as fallback if only one
    if len(prog_names) == 1:
        return next(iter(prog_names.values()))
    return None


def _assign_subject_type_if_missing(
    form: Any, st_names: dict, enc_to_subject: dict, sector_info: dict | None,
) -> None:
    """Assign subjectTypeName if not already set."""
    if form.subjectTypeName:
        return

    name_lower = form.name.strip().lower()

    # Check enc_to_subject mapping
    if name_lower in enc_to_subject:
        form.subjectTypeName = enc_to_subject[name_lower]
        return

    # For registration forms, infer from form name
    if form.formType == "IndividualProfile":
        for st_lower, st_name in st_names.items():
            if st_lower in name_lower:
                form.subjectTypeName = st_name
                return

    # For sector rules
    if sector_info and sector_info.get("rules"):
        rules = sector_info["rules"]
        # Attendance/assessment → Group subject
        if any(kw in name_lower for kw in ["attendance", "assessment", "inspection"]):
            if "attendance_goes_on" in rules or "assessment_goes_on" in rules:
                # Find the Group subject type
                for st_lower, st_name in st_names.items():
                    from app.services.srs_parser import _normalize
                    # Check if this is a Group/Center type subject
                    if st_lower in name_lower:
                        form.subjectTypeName = st_name
                        return

        # Village/community meetings → Village subject
        if any(kw in name_lower for kw in ["village", "panchayat", "gram sabha", "manch"]):
            for st_lower, st_name in st_names.items():
                if "village" in st_lower or st_lower in name_lower:
                    form.subjectTypeName = st_name
                    return
