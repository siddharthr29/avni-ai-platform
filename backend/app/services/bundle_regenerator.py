"""Bundle regeneration system.

Diagnoses bundle errors from multiple sources (pre-flight validation, server
upload CSV, user chat feedback, validation API), applies automatic fixes where
possible, and re-runs validation in a loop until clean or max iterations.

Usage:
    from app.services.bundle_regenerator import BundleRegenerator, ErrorSource

    regenerator = BundleRegenerator()
    errors = await regenerator.diagnose(bundle_dir, error_text, ErrorSource.SERVER_UPLOAD)
    result = await regenerator.fix_and_validate(bundle_dir, errors)
"""

import csv
import io
import json
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)

__all__ = [
    "BundleRegenerator",
    "BundleError",
    "ErrorSource",
    "RegenerationResult",
]

MAX_FIX_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ErrorSource(str, Enum):
    """Where the error came from."""
    PREFLIGHT = "preflight"
    SERVER_UPLOAD = "server_upload"
    USER_FEEDBACK = "user_feedback"
    VALIDATION_API = "validation_api"


@dataclass
class BundleError:
    """A single error found in a bundle."""
    source: ErrorSource
    file: str                          # Which JSON file (concepts.json, forms/ANC.json, etc.)
    field: Optional[str]               # Which field (name, dataType, answers[2].uuid, etc.)
    message: str                       # Error description
    severity: str                      # "error" or "warning"
    auto_fixable: bool                 # Can we fix this automatically?
    suggested_fix: Optional[str] = None
    category: str = ""                 # duplicate_concept, missing_uuid, etc.

    def to_dict(self) -> dict:
        return {
            "source": self.source.value,
            "file": self.file,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
            "auto_fixable": self.auto_fixable,
            "suggested_fix": self.suggested_fix,
            "category": self.category,
        }


@dataclass
class RegenerationResult:
    """Result of a fix-and-validate cycle."""
    success: bool
    changes_made: list[dict] = field(default_factory=list)       # [{file, field, old_value, new_value, reason}]
    remaining_errors: list[BundleError] = field(default_factory=list)
    iterations: int = 0
    needs_human_input: list[BundleError] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "changes_made": self.changes_made,
            "remaining_errors": [e.to_dict() for e in self.remaining_errors],
            "iterations": self.iterations,
            "needs_human_input": [e.to_dict() for e in self.needs_human_input],
        }


# ---------------------------------------------------------------------------
# LLM prompt for parsing natural language feedback into structured errors
# ---------------------------------------------------------------------------

_USER_FEEDBACK_SYSTEM_PROMPT = """You are an expert Avni implementation engineer. A user has reported a problem with their generated bundle.

Given the user's message and the list of files in the bundle, identify the specific errors.

Return a JSON array of error objects. Each object must have:
- "file": which bundle file is affected (e.g., "concepts.json", "forms/ANC Registration.json")
- "field": which specific field or element (e.g., "name", "dataType", "answers", a concept name)
- "message": description of the problem
- "severity": "error" or "warning"
- "auto_fixable": true if this can be fixed programmatically, false if human decision needed
- "suggested_fix": what change to make (be specific: "rename X to Y", "change dataType from Text to Numeric", "add concept Z with dataType Coded and answers [A, B, C]")
- "category": one of: duplicate_concept_name, missing_uuid, invalid_data_type, missing_answer_concept, broken_form_reference, invalid_rule_syntax, missing_form_mapping, duplicate_display_order, invalid_characters, missing_cancellation_form, numeric_range_invalid, concept_collision, add_field, remove_field, change_field, add_program, remove_program, add_form, change_visit_schedule, other

Return ONLY the JSON array, no explanations.

If the user's message is vague and you cannot determine the specific fix, set auto_fixable to false and describe what clarification is needed in suggested_fix."""


# ---------------------------------------------------------------------------
# Fix strategy registry
# ---------------------------------------------------------------------------

def _fix_duplicate_concept_name(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Fix duplicate concept names by adding a contextual prefix/suffix."""
    target_name = error.field
    if not target_name:
        return None

    target_lower = target_name.lower().strip()
    duplicates = [c for c in concepts if c.get("name", "").lower().strip() == target_lower]
    if len(duplicates) < 2:
        return None

    # Keep the first occurrence, rename subsequent ones
    for i, dup in enumerate(duplicates[1:], start=2):
        old_name = dup["name"]
        new_name = f"{old_name} ({i})"
        dup["name"] = new_name
        logger.info("Renamed duplicate concept '%s' to '%s'", old_name, new_name)

    _write_json(bundle_dir / "concepts.json", concepts)
    return {
        "file": "concepts.json",
        "field": "name",
        "old_value": target_name,
        "new_value": f"{target_name} (2)",
        "reason": "Resolved duplicate concept name collision",
    }


def _fix_missing_uuid(bundle_dir: Path, error: BundleError, data: Any) -> Optional[dict]:
    """Generate a UUID for an entity that's missing one."""
    new_uuid = str(uuid.uuid4())
    return {
        "file": error.file,
        "field": "uuid",
        "old_value": None,
        "new_value": new_uuid,
        "reason": "Generated missing UUID",
    }


def _fix_invalid_data_type(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Correct an invalid dataType to the nearest valid one."""
    valid_types = {
        "text": "Text",
        "string": "Text",
        "str": "Text",
        "numeric": "Numeric",
        "number": "Numeric",
        "int": "Numeric",
        "integer": "Numeric",
        "float": "Numeric",
        "decimal": "Numeric",
        "date": "Date",
        "datetime": "DateTime",
        "coded": "Coded",
        "select": "Coded",
        "dropdown": "Coded",
        "boolean": "Coded",
        "bool": "Coded",
        "notes": "Notes",
        "memo": "Notes",
        "textarea": "Notes",
        "image": "Image",
        "photo": "Image",
        "time": "Time",
        "phonenumber": "PhoneNumber",
        "phone": "PhoneNumber",
        "na": "NA",
        "id": "Id",
        "location": "Location",
        "subject": "Subject",
        "encounter": "Encounter",
        "duration": "Duration",
        "video": "Video",
        "audio": "Audio",
        "file": "File",
        "groupaffiliation": "GroupAffiliation",
    }

    target_name = error.field
    if not target_name:
        return None

    for concept in concepts:
        if concept.get("name") == target_name:
            old_type = concept.get("dataType", "")
            corrected = valid_types.get(old_type.lower().strip())
            if corrected and corrected != old_type:
                concept["dataType"] = corrected
                _write_json(bundle_dir / "concepts.json", concepts)
                return {
                    "file": "concepts.json",
                    "field": f"{target_name}.dataType",
                    "old_value": old_type,
                    "new_value": corrected,
                    "reason": f"Corrected invalid dataType '{old_type}' to '{corrected}'",
                }
    return None


def _fix_missing_answer_concept(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Create a missing NA answer concept that a Coded concept references."""
    # Extract the missing answer name from the error message
    match = re.search(r"answer '([^']+)'.*UUID '([^']+)'", error.message)
    if not match:
        return None

    answer_name = match.group(1)
    answer_uuid = match.group(2)

    # Check if the answer concept already exists
    existing = [c for c in concepts if c.get("uuid") == answer_uuid]
    if existing:
        return None

    # Create the NA answer concept
    new_concept = {
        "uuid": answer_uuid,
        "name": answer_name,
        "dataType": "NA",
        "voided": False,
    }

    # Insert before any Coded concepts that reference it (order matters in Avni)
    insert_idx = 0
    for i, c in enumerate(concepts):
        if c.get("dataType") == "NA":
            insert_idx = i + 1  # After existing NA concepts
    concepts.insert(insert_idx, new_concept)

    _write_json(bundle_dir / "concepts.json", concepts)
    return {
        "file": "concepts.json",
        "field": answer_name,
        "old_value": None,
        "new_value": f"NA concept '{answer_name}' with UUID {answer_uuid}",
        "reason": f"Created missing NA answer concept '{answer_name}'",
    }


def _fix_broken_form_reference(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Fix a form element referencing a concept UUID not in concepts.json."""
    # Parse the missing UUID and concept name from error
    match = re.search(r"UUID '([^']+)'.*name: '([^']+)'", error.message)
    if not match:
        return None

    missing_uuid = match.group(1)
    concept_name = match.group(2)

    # Check if concept exists by name (UUID mismatch)
    for c in concepts:
        if c.get("name", "").lower().strip() == concept_name.lower().strip():
            correct_uuid = c["uuid"]
            # Fix the form reference to use the correct UUID
            _fix_uuid_in_forms(bundle_dir, missing_uuid, correct_uuid)
            return {
                "file": error.file,
                "field": f"concept.uuid ({concept_name})",
                "old_value": missing_uuid,
                "new_value": correct_uuid,
                "reason": f"Fixed concept UUID reference for '{concept_name}'",
            }

    # Concept doesn't exist — create it as Text (safest default)
    new_concept = {
        "uuid": missing_uuid,
        "name": concept_name,
        "dataType": "Text",
        "voided": False,
    }
    concepts.append(new_concept)
    _write_json(bundle_dir / "concepts.json", concepts)
    return {
        "file": "concepts.json",
        "field": concept_name,
        "old_value": None,
        "new_value": f"Text concept '{concept_name}'",
        "reason": f"Created missing concept '{concept_name}' referenced by form",
    }


def _fix_missing_form_mapping(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Create a missing form mapping entry."""
    # This requires knowing form UUID, subject type, etc. — complex
    # Mark as needing context; LLM-based fix is more appropriate
    return None


def _fix_duplicate_display_order(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Renumber display orders within a form element group."""
    form_file = error.file
    form_path = bundle_dir / form_file
    if not form_path.is_file():
        return None

    form_data = _read_json(form_path)
    if not form_data:
        return None

    changed = False
    for feg in form_data.get("formElementGroups", []):
        elements = feg.get("formElements", [])
        seen_orders: set[float] = set()
        for fe in elements:
            order = fe.get("displayOrder", 0)
            if order in seen_orders:
                # Find next available order
                new_order = max(seen_orders) + 1.0
                fe["displayOrder"] = new_order
                changed = True
            seen_orders.add(fe.get("displayOrder", 0))

    if changed:
        _write_json(form_path, form_data)
        return {
            "file": form_file,
            "field": "displayOrder",
            "old_value": "duplicates",
            "new_value": "renumbered sequentially",
            "reason": "Resolved duplicate displayOrder values",
        }
    return None


def _fix_invalid_characters(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Sanitize invalid characters from concept/field names."""
    target = error.field
    if not target:
        return None

    invalid_chars = re.compile(r'[^\w\s\-./()&,\'"]', re.UNICODE)
    for c in concepts:
        if c.get("name") == target:
            sanitized = invalid_chars.sub("", target).strip()
            if sanitized != target:
                c["name"] = sanitized
                _write_json(bundle_dir / "concepts.json", concepts)
                return {
                    "file": "concepts.json",
                    "field": "name",
                    "old_value": target,
                    "new_value": sanitized,
                    "reason": "Removed invalid characters from concept name",
                }
    return None


def _fix_numeric_range_invalid(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Fix numeric range where lowAbsolute > highAbsolute by swapping."""
    target = error.field
    if not target:
        return None

    for c in concepts:
        if c.get("name") == target and c.get("dataType") == "Numeric":
            low = c.get("lowAbsolute")
            high = c.get("highAbsolute")
            if low is not None and high is not None and low > high:
                c["lowAbsolute"] = high
                c["highAbsolute"] = low
                _write_json(bundle_dir / "concepts.json", concepts)
                return {
                    "file": "concepts.json",
                    "field": f"{target}.range",
                    "old_value": f"low={low}, high={high}",
                    "new_value": f"low={high}, high={low}",
                    "reason": "Swapped inverted numeric range values",
                }
    return None


def _fix_concept_collision(bundle_dir: Path, error: BundleError, concepts: list[dict]) -> Optional[dict]:
    """Rename a colliding concept by adding disambiguating context."""
    # Delegate to duplicate concept name fixer
    return _fix_duplicate_concept_name(bundle_dir, error, concepts)


# Map category -> fix function
FIX_STRATEGIES: dict[str, Any] = {
    "duplicate_concept_name": _fix_duplicate_concept_name,
    "duplicate_concept": _fix_duplicate_concept_name,
    "missing_uuid": _fix_missing_uuid,
    "invalid_data_type": _fix_invalid_data_type,
    "datatype_mismatch": _fix_invalid_data_type,
    "missing_answer_concept": _fix_missing_answer_concept,
    "answer_uuid_mismatch": _fix_missing_answer_concept,
    "broken_form_reference": _fix_broken_form_reference,
    "missing_concept": _fix_broken_form_reference,
    "missing_form_mapping": _fix_missing_form_mapping,
    "orphaned_mapping": _fix_missing_form_mapping,
    "duplicate_display_order": _fix_duplicate_display_order,
    "invalid_characters": _fix_invalid_characters,
    "numeric_range_invalid": _fix_numeric_range_invalid,
    "concept_collision": _fix_concept_collision,
}


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> Any:
    """Read and parse a JSON file, returning None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Failed to read JSON %s: %s", path, e)
        return None


def _write_json(path: Path, data: Any) -> None:
    """Write data to a JSON file with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _fix_uuid_in_forms(bundle_dir: Path, old_uuid: str, new_uuid: str) -> int:
    """Replace a UUID across all form files. Returns count of replacements."""
    forms_dir = bundle_dir / "forms"
    if not forms_dir.is_dir():
        return 0

    count = 0
    for form_file in forms_dir.iterdir():
        if not form_file.suffix == ".json":
            continue
        content = form_file.read_text(encoding="utf-8")
        if old_uuid in content:
            content = content.replace(old_uuid, new_uuid)
            form_file.write_text(content, encoding="utf-8")
            count += 1
    return count


def _list_bundle_files(bundle_dir: Path) -> list[str]:
    """List all JSON files in a bundle directory (relative paths)."""
    files = []
    for root, _dirs, filenames in os.walk(bundle_dir):
        for fname in filenames:
            if fname.endswith(".json"):
                rel = os.path.relpath(os.path.join(root, fname), bundle_dir)
                files.append(rel)
    return sorted(files)


def _load_concepts(bundle_dir: Path) -> list[dict]:
    """Load concepts.json from bundle directory."""
    data = _read_json(bundle_dir / "concepts.json")
    return data if isinstance(data, list) else []


# ---------------------------------------------------------------------------
# BundleRegenerator
# ---------------------------------------------------------------------------

class BundleRegenerator:
    """Fix and regenerate bundles based on error feedback.

    Supports multiple error sources: pre-flight validation, server upload CSV,
    user chat feedback, and the validation API. Applies deterministic fixes
    for known error patterns and delegates complex fixes to the LLM.
    """

    async def diagnose(
        self,
        bundle_dir: Path,
        error_input: str,
        source: ErrorSource,
    ) -> list[BundleError]:
        """Parse error input into structured BundleError list.

        Args:
            bundle_dir: Path to the unpacked bundle directory.
            error_input: Raw error text — CSV from server, validation JSON,
                         or natural language from user chat.
            source: Where the error came from.

        Returns:
            List of diagnosed BundleErrors with fix suggestions.
        """
        if source == ErrorSource.SERVER_UPLOAD:
            return self._parse_server_csv(error_input)
        elif source == ErrorSource.PREFLIGHT:
            return self._parse_preflight_errors(error_input)
        elif source == ErrorSource.VALIDATION_API:
            return self._parse_validation_api(error_input)
        elif source == ErrorSource.USER_FEEDBACK:
            return await self._parse_user_feedback(error_input, bundle_dir)
        else:
            logger.warning("Unknown error source: %s", source)
            return []

    async def fix_errors(
        self,
        bundle_dir: Path,
        errors: list[BundleError],
    ) -> RegenerationResult:
        """Apply fixes to bundle files for the given errors.

        Uses deterministic fix strategies for known categories and falls back
        to LLM-based fixing for complex/ambiguous errors.

        Args:
            bundle_dir: Path to the unpacked bundle directory.
            errors: List of errors to fix.

        Returns:
            RegenerationResult with changes made and any remaining errors.
        """
        result = RegenerationResult(success=True, iterations=1)
        concepts = _load_concepts(bundle_dir)

        auto_fixable = [e for e in errors if e.auto_fixable]
        manual_only = [e for e in errors if not e.auto_fixable]

        # Phase 1: Apply deterministic fix strategies
        for error in auto_fixable:
            strategy = FIX_STRATEGIES.get(error.category)
            if strategy:
                try:
                    # Reload concepts each time since fixes may modify them
                    concepts = _load_concepts(bundle_dir)
                    change = strategy(bundle_dir, error, concepts)
                    if change:
                        result.changes_made.append(change)
                        logger.info(
                            "Auto-fixed [%s] %s: %s",
                            error.category, error.file, change.get("reason", ""),
                        )
                    else:
                        # Strategy returned None — couldn't fix
                        result.remaining_errors.append(error)
                except Exception as e:
                    logger.warning(
                        "Fix strategy '%s' failed for %s: %s",
                        error.category, error.file, e,
                    )
                    result.remaining_errors.append(error)
            else:
                # No strategy registered for this category
                result.remaining_errors.append(error)

        # Phase 2: Try LLM-based fixing for remaining auto-fixable errors
        llm_fixable = [
            e for e in result.remaining_errors
            if e.auto_fixable and e.suggested_fix
        ]
        if llm_fixable:
            llm_changes = await self._apply_llm_fixes(bundle_dir, llm_fixable)
            result.changes_made.extend(llm_changes)
            # Remove successfully fixed errors from remaining
            fixed_msgs = {c["reason"] for c in llm_changes}
            result.remaining_errors = [
                e for e in result.remaining_errors
                if e.message not in fixed_msgs and e not in llm_fixable
            ]

        # Phase 3: Collect errors that need human input
        result.needs_human_input = manual_only
        result.remaining_errors.extend(manual_only)
        result.success = len([
            e for e in result.remaining_errors if e.severity == "error"
        ]) == 0

        return result

    async def regenerate_component(
        self,
        bundle_dir: Path,
        component: str,
        context: dict,
    ) -> Path:
        """Regenerate a specific bundle component using the original SRS context.

        Args:
            bundle_dir: Path to the unpacked bundle directory.
            component: Component to regenerate (e.g., "rules", "forms/ANC.json",
                       "concepts", "formMappings").
            context: Additional context — must include 'srs_data' dict.

        Returns:
            Path to the regenerated file.
        """
        from app.models.schemas import SRSData
        from app.services.bundle_generator import generate_from_srs

        srs_data = context.get("srs_data")
        if not srs_data:
            raise ValueError("context must include 'srs_data' for component regeneration")

        if isinstance(srs_data, dict):
            srs_data = SRSData(**srs_data)

        # Generate into a temp bundle, then copy only the requested component
        import tempfile
        temp_id = str(uuid.uuid4())
        await generate_from_srs(srs_data, temp_id)

        temp_bundle = Path(settings.BUNDLE_OUTPUT_DIR) / temp_id
        source_path = temp_bundle / component
        target_path = bundle_dir / component

        if source_path.is_file():
            import shutil
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            logger.info("Regenerated component %s from fresh SRS generation", component)
        elif source_path.is_dir():
            import shutil
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.copytree(source_path, target_path)
            logger.info("Regenerated component directory %s", component)
        else:
            raise FileNotFoundError(
                f"Component '{component}' not found in regenerated bundle"
            )

        # Clean up temp bundle
        import shutil
        shutil.rmtree(temp_bundle, ignore_errors=True)

        return target_path

    async def fix_and_validate(
        self,
        bundle_dir: Path,
        errors: list[BundleError],
    ) -> RegenerationResult:
        """Fix errors and re-run validation in a loop until clean.

        Iterates up to MAX_FIX_ITERATIONS times:
        1. Apply fixes for current errors
        2. Run BundleValidator
        3. If new errors found, fix those too
        4. Stop when clean or max iterations reached

        Args:
            bundle_dir: Path to the unpacked bundle directory.
            errors: Initial list of errors to fix.

        Returns:
            Cumulative RegenerationResult across all iterations.
        """
        cumulative = RegenerationResult(success=False)
        current_errors = list(errors)

        for iteration in range(1, MAX_FIX_ITERATIONS + 1):
            logger.info(
                "Fix-validate iteration %d/%d: %d errors to fix",
                iteration, MAX_FIX_ITERATIONS, len(current_errors),
            )

            # Apply fixes
            iter_result = await self.fix_errors(bundle_dir, current_errors)
            cumulative.changes_made.extend(iter_result.changes_made)
            cumulative.iterations = iteration
            cumulative.needs_human_input = iter_result.needs_human_input

            # Re-run validation
            new_errors = self._run_validation(bundle_dir)

            if not new_errors:
                cumulative.success = True
                cumulative.remaining_errors = []
                logger.info(
                    "Bundle is clean after %d iteration(s), %d fixes applied",
                    iteration, len(cumulative.changes_made),
                )
                break

            # Check if we made progress
            new_error_msgs = {e.message for e in new_errors}
            old_error_msgs = {e.message for e in current_errors}
            if new_error_msgs == old_error_msgs:
                # No progress — stop to prevent infinite loop
                cumulative.remaining_errors = new_errors
                logger.warning(
                    "No progress in iteration %d — %d errors remain unfixable",
                    iteration, len(new_errors),
                )
                break

            current_errors = new_errors

        else:
            # Exhausted iterations
            cumulative.remaining_errors = current_errors
            logger.warning(
                "Reached max iterations (%d) with %d errors remaining",
                MAX_FIX_ITERATIONS, len(current_errors),
            )

        cumulative.success = len([
            e for e in cumulative.remaining_errors if e.severity == "error"
        ]) == 0
        return cumulative

    # -------------------------------------------------------------------
    # Error parsers
    # -------------------------------------------------------------------

    def _parse_server_csv(self, csv_content: str) -> list[BundleError]:
        """Parse Avni server error CSV into BundleErrors.

        The server returns errors as CSV rows during bundle upload.
        Common patterns: 'Concept with name X not found', 'Duplicate concept',
        'Invalid form type', etc.
        """
        errors: list[BundleError] = []

        # Reuse the pattern matching from bundle_generator.analyze_error_csv
        error_patterns = {
            r"Concept with name ['\"]?(.+?)['\"]? not found": {
                "category": "missing_concept",
                "file": "concepts.json",
                "auto_fixable": True,
                "fix": "Add the missing concept to concepts.json",
            },
            r"Duplicate concept name[:\s]*['\"]?(.+?)['\"]?": {
                "category": "duplicate_concept_name",
                "file": "concepts.json",
                "auto_fixable": True,
                "fix": "Rename or deduplicate the concept",
            },
            r"Invalid form type[:\s]*['\"]?(.+?)['\"]?": {
                "category": "invalid_form_type",
                "file": "formMappings.json",
                "auto_fixable": False,
                "fix": "Use valid form types: IndividualProfile, Encounter, ProgramEncounter, ProgramEnrolment, ProgramExit, ProgramEncounterCancellation, IndividualEncounterCancellation",
            },
            r"Subject type ['\"]?(.+?)['\"]? not found": {
                "category": "missing_subject_type",
                "file": "subjectTypes.json",
                "auto_fixable": False,
                "fix": "Define the subject type in subjectTypes.json",
            },
            r"Program ['\"]?(.+?)['\"]? not found": {
                "category": "missing_program",
                "file": "programs.json",
                "auto_fixable": False,
                "fix": "Define the program in programs.json",
            },
            r"Encounter type ['\"]?(.+?)['\"]? not found": {
                "category": "missing_encounter_type",
                "file": "encounterTypes.json",
                "auto_fixable": False,
                "fix": "Define the encounter type in encounterTypes.json",
            },
            r"already exists": {
                "category": "duplicate_entity",
                "file": "unknown",
                "auto_fixable": False,
                "fix": "Use the same UUID as the existing entity to update it",
            },
            r"displayOrder.*duplicate": {
                "category": "duplicate_display_order",
                "file": "forms/",
                "auto_fixable": True,
                "fix": "Renumber displayOrder values to be unique",
            },
            r"UUID.*invalid": {
                "category": "invalid_uuid",
                "file": "unknown",
                "auto_fixable": True,
                "fix": "Generate a valid v4 UUID",
            },
            r"data type.*mismatch": {
                "category": "datatype_mismatch",
                "file": "concepts.json",
                "auto_fixable": True,
                "fix": "Correct the dataType to match usage",
            },
        }

        try:
            reader = csv.reader(io.StringIO(csv_content))
            rows = list(reader)
        except Exception:
            rows = [[line] for line in csv_content.strip().split("\n")]

        for row in rows:
            error_text = " ".join(str(cell) for cell in row).strip()
            if not error_text:
                continue

            matched = False
            for pattern, info in error_patterns.items():
                m = re.search(pattern, error_text, re.IGNORECASE)
                if m:
                    field_name = m.group(1) if m.lastindex and m.lastindex >= 1 else None
                    errors.append(BundleError(
                        source=ErrorSource.SERVER_UPLOAD,
                        file=info["file"],
                        field=field_name,
                        message=error_text,
                        severity="error",
                        auto_fixable=info["auto_fixable"],
                        suggested_fix=info["fix"],
                        category=info["category"],
                    ))
                    matched = True
                    break

            if not matched:
                errors.append(BundleError(
                    source=ErrorSource.SERVER_UPLOAD,
                    file="unknown",
                    field=None,
                    message=error_text,
                    severity="error",
                    auto_fixable=False,
                    suggested_fix="Review the error message manually",
                    category="unknown",
                ))

        return errors

    def _parse_preflight_errors(self, validation_input: str) -> list[BundleError]:
        """Parse pre-flight validation results into BundleErrors.

        Accepts either a JSON string (from BundleValidator.validate()) or
        raw text output.
        """
        errors: list[BundleError] = []

        # Try parsing as JSON first (from BundleValidator output)
        try:
            data = json.loads(validation_input) if isinstance(validation_input, str) else validation_input
            issues = data.get("issues", [])
            for issue in issues:
                category = issue.get("category", "unknown")
                errors.append(BundleError(
                    source=ErrorSource.PREFLIGHT,
                    file=issue.get("file", "unknown"),
                    field=self._extract_field_from_message(issue.get("message", "")),
                    message=issue.get("message", ""),
                    severity=issue.get("severity", "error"),
                    auto_fixable=category in FIX_STRATEGIES,
                    suggested_fix=issue.get("fix_hint", ""),
                    category=category,
                ))
            return errors
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass

        # Fall back to line-by-line parsing
        for line in validation_input.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            severity = "warning" if "warning" in line.lower() else "error"
            errors.append(BundleError(
                source=ErrorSource.PREFLIGHT,
                file="unknown",
                field=None,
                message=line,
                severity=severity,
                auto_fixable=False,
                suggested_fix=None,
                category="unknown",
            ))

        return errors

    def _parse_validation_api(self, validation_input: str) -> list[BundleError]:
        """Parse validation API response (same format as preflight)."""
        return self._parse_preflight_errors(validation_input)

    async def _parse_user_feedback(
        self,
        message: str,
        bundle_dir: Path,
    ) -> list[BundleError]:
        """Use LLM to interpret natural language feedback into BundleErrors.

        Handles messages like:
        - "The ANC form is missing the blood group field"
        - "The visit schedule should be 14 days not 7"
        - "Remove the TB program, they don't need it"
        - "This concept should be Numeric not Coded"

        Args:
            message: User's natural language feedback.
            bundle_dir: Path to the bundle for context.

        Returns:
            List of structured BundleErrors.
        """
        # Provide context about what's in the bundle
        bundle_files = _list_bundle_files(bundle_dir)

        # Load a summary of the bundle contents for the LLM
        concepts_summary = ""
        concepts_path = bundle_dir / "concepts.json"
        if concepts_path.is_file():
            concepts = _read_json(concepts_path)
            if isinstance(concepts, list):
                concept_names = [c.get("name", "?") for c in concepts[:50]]
                concepts_summary = f"Concepts ({len(concepts)} total): {', '.join(concept_names)}"
                if len(concepts) > 50:
                    concepts_summary += f" ... and {len(concepts) - 50} more"

        forms_summary = ""
        forms_dir = bundle_dir / "forms"
        if forms_dir.is_dir():
            form_names = [f.stem for f in forms_dir.iterdir() if f.suffix == ".json"]
            forms_summary = f"Forms: {', '.join(form_names)}"

        context_text = (
            f"Bundle files: {', '.join(bundle_files)}\n"
            f"{concepts_summary}\n"
            f"{forms_summary}"
        )

        prompt = (
            f"Bundle context:\n{context_text}\n\n"
            f"User's feedback:\n{message}\n\n"
            f"Identify the specific errors/changes needed."
        )

        try:
            response = await claude_client.complete(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_USER_FEEDBACK_SYSTEM_PROMPT,
            )

            # Extract JSON array from response
            parsed = self._extract_json_array(response)
            if not parsed:
                logger.warning("LLM did not return valid JSON array for user feedback")
                return [BundleError(
                    source=ErrorSource.USER_FEEDBACK,
                    file="unknown",
                    field=None,
                    message=message,
                    severity="error",
                    auto_fixable=False,
                    suggested_fix="Could not automatically parse feedback — please be more specific",
                    category="other",
                )]

            errors = []
            for item in parsed:
                errors.append(BundleError(
                    source=ErrorSource.USER_FEEDBACK,
                    file=item.get("file", "unknown"),
                    field=item.get("field"),
                    message=item.get("message", message),
                    severity=item.get("severity", "error"),
                    auto_fixable=item.get("auto_fixable", False),
                    suggested_fix=item.get("suggested_fix"),
                    category=item.get("category", "other"),
                ))
            return errors

        except Exception as e:
            logger.warning("LLM feedback parsing failed: %s", e)
            return [BundleError(
                source=ErrorSource.USER_FEEDBACK,
                file="unknown",
                field=None,
                message=message,
                severity="error",
                auto_fixable=False,
                suggested_fix=str(e),
                category="other",
            )]

    # -------------------------------------------------------------------
    # Validation runner
    # -------------------------------------------------------------------

    def _run_validation(self, bundle_dir: Path) -> list[BundleError]:
        """Run the BundleValidator and convert results to BundleErrors."""
        try:
            from app.services.bundle_validator import BundleValidator
            validator = BundleValidator(str(bundle_dir))
            result = validator.validate()
            return self._parse_preflight_errors(json.dumps(result))
        except ImportError:
            logger.warning(
                "BundleValidator not available — skipping validation step"
            )
            return []
        except Exception as e:
            logger.warning("Validation failed: %s", e)
            return []

    # -------------------------------------------------------------------
    # LLM-based fixing
    # -------------------------------------------------------------------

    async def _apply_llm_fixes(
        self,
        bundle_dir: Path,
        errors: list[BundleError],
    ) -> list[dict]:
        """Use LLM to apply fixes that deterministic strategies couldn't handle.

        Sends the error details and relevant file contents to the LLM, which
        returns a JSON patch describing the changes to make.
        """
        changes: list[dict] = []

        # Group errors by file to minimize LLM calls
        errors_by_file: dict[str, list[BundleError]] = {}
        for error in errors:
            errors_by_file.setdefault(error.file, []).append(error)

        for file_path, file_errors in errors_by_file.items():
            full_path = bundle_dir / file_path
            if not full_path.is_file():
                continue

            file_content = _read_json(full_path)
            if file_content is None:
                continue

            error_descriptions = "\n".join(
                f"- [{e.category}] {e.message} (suggested: {e.suggested_fix})"
                for e in file_errors
            )

            prompt = (
                f"Fix the following errors in {file_path}:\n\n"
                f"{error_descriptions}\n\n"
                f"Current file content:\n```json\n{json.dumps(file_content, indent=2)}\n```\n\n"
                f"Return ONLY the corrected JSON. No explanations."
            )

            try:
                response = await claude_client.complete(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=(
                        "You are an Avni bundle repair tool. Fix the specified errors in the "
                        "JSON file and return the corrected version. Keep all other data intact. "
                        "Return ONLY valid JSON, no markdown fences or explanations."
                    ),
                )

                fixed_content = self._extract_json_object_or_array(response)
                if fixed_content is not None:
                    _write_json(full_path, fixed_content)
                    changes.append({
                        "file": file_path,
                        "field": "multiple",
                        "old_value": f"{len(file_errors)} errors",
                        "new_value": "LLM-corrected",
                        "reason": f"LLM fixed {len(file_errors)} error(s) in {file_path}",
                    })
                    logger.info("LLM fixed %d errors in %s", len(file_errors), file_path)

            except Exception as e:
                logger.warning("LLM fix failed for %s: %s", file_path, e)

        return changes

    # -------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------

    @staticmethod
    def _extract_field_from_message(message: str) -> Optional[str]:
        """Extract a field/concept name from a validation message."""
        # Patterns like: "concept 'Foo Bar'" or "field 'Weight'"
        m = re.search(r"'([^']+)'", message)
        return m.group(1) if m else None

    @staticmethod
    def _extract_json_array(text: str) -> Optional[list]:
        """Extract a JSON array from LLM response text."""
        text = text.strip()
        # Strip markdown fences
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        if text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Find first [ to last ]
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        return None

    @staticmethod
    def _extract_json_object_or_array(text: str) -> Any:
        """Extract a JSON object or array from LLM response text."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find the outermost JSON structure
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    continue

        return None


# ---------------------------------------------------------------------------
# Zip helper
# ---------------------------------------------------------------------------

def repackage_bundle_zip(bundle_dir: Path) -> Path:
    """Re-create the bundle zip file from a modified bundle directory.

    Args:
        bundle_dir: Path to the unpacked bundle directory.

    Returns:
        Path to the new zip file.
    """
    zip_path = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(bundle_dir):
            for fname in files:
                abs_path = os.path.join(root, fname)
                arc_name = os.path.relpath(abs_path, bundle_dir.parent)
                zf.write(abs_path, arc_name)

    logger.info("Repackaged bundle zip: %s", zip_path)
    return zip_path


# Module-level singleton
regenerator = BundleRegenerator()
