"""Intent-specific handlers for chat actions.

Handles bundle regeneration, bundle correction, bundle creation (text + XLSX),
file attachment processing, and clarification workflows.
"""
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any, AsyncGenerator

from app.config import settings
from app.models.schemas import IntentType, SSEEventType
from app.services.claude_client import claude_client
from app.services.context_manager import (
    _bundle_pending,
    _last_bundle,
    get_history,
    save_message,
)

logger = logging.getLogger(__name__)


async def handle_bundle_regenerate(
    session_id: str,
    message: str,
    authenticated_user_id: str,
) -> AsyncGenerator[dict, None]:
    """Handle bundle_regenerate action — fix errors in last generated bundle.

    Yields SSE event dicts. Returns None if should fall through to normal chat.
    """
    if session_id not in _last_bundle:
        return

    try:
        from app.services.bundle_regenerator import BundleRegenerator, ErrorSource
        from app.services.bundle_generator import get_bundle_file_tree

        prev = _last_bundle[session_id]
        prev_bundle_id = prev["bundle_id"]
        bundle_dir = Path(os.path.join(settings.BUNDLE_OUTPUT_DIR, prev_bundle_id))

        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.PROGRESS.value,
                "content": f"Diagnosing errors in bundle `{prev_bundle_id[:8]}`...",
                "metadata": {"progress": {"step": "Diagnosing errors", "current": 1, "total": 3}},
            }),
        }

        regen = BundleRegenerator()

        # Detect if user pasted CSV or just described the error
        is_csv = any(
            kw in message.lower()
            for kw in ["concept with name", "not found", "duplicate concept", "invalid form type"]
        ) or "," in message and "\n" in message
        source = ErrorSource.SERVER_UPLOAD if is_csv else ErrorSource.USER_FEEDBACK

        errors = await regen.diagnose(bundle_dir, message, source)

        if not errors:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": "I couldn't identify specific errors from your message. Could you paste the exact error output or describe the problem more specifically?",
                }),
            }
            yield {
                "event": "message",
                "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
            }
            await save_message(session_id, "assistant", "Could not identify errors — asked for clarification.", user_id=authenticated_user_id)
            return

        auto_count = sum(1 for e in errors if e.auto_fixable)
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.PROGRESS.value,
                "content": f"Found {len(errors)} error(s), {auto_count} auto-fixable. Applying fixes...",
                "metadata": {"progress": {"step": "Fixing errors", "current": 2, "total": 3}},
            }),
        }

        result = await regen.fix_and_validate(bundle_dir, errors)

        # Repackage the zip
        from app.services.bundle_regenerator import repackage_bundle_zip
        repackage_bundle_zip(bundle_dir)

        # Build summary
        changes_text = "\n".join(
            f"- **{c['file']}**: {c['reason']}"
            for c in result.changes_made
        ) if result.changes_made else "No changes were needed."

        remaining_text = ""
        if result.remaining_errors:
            remaining_text = "\n\n**Remaining issues:**\n" + "\n".join(
                f"- [{e.severity}] {e.message}"
                for e in result.remaining_errors
            )

        human_text = ""
        if result.needs_human_input:
            human_text = "\n\n**Needs your input:**\n" + "\n".join(
                f"- {e.message} — {e.suggested_fix or 'please clarify'}"
                for e in result.needs_human_input
            )

        status_emoji = "fixed" if result.success else "partially fixed"
        summary = (
            f"Bundle {status_emoji} after {result.iterations} iteration(s)!\n\n"
            f"**Changes made:**\n{changes_text}"
            f"{remaining_text}{human_text}\n\n"
            f"**Bundle ID:** `{prev_bundle_id[:8]}`\n"
            f"You can download the updated ZIP or tell me about more issues."
        )

        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": summary,
            }),
        }

        file_tree = get_bundle_file_tree(prev_bundle_id)
        if file_tree:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "bundle_ready",
                    "content": "",
                    "metadata": {
                        "bundleId": prev_bundle_id,
                        "downloadUrl": f"/api/bundle/{prev_bundle_id}/download",
                        "files": file_tree,
                        "regenerated": True,
                        "fixes_applied": len(result.changes_made),
                    },
                }),
            }

        await save_message(session_id, "assistant", summary, user_id=authenticated_user_id)
        yield {
            "event": "message",
            "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
        }

    except Exception as e:
        logger.exception("Bundle regeneration from chat failed")
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": f"Error fixing failed: {str(e)}\n\nPlease paste the exact error output and I'll try again.\n\n",
            }),
        }
        # Caller should fall through to normal LLM chat


async def handle_bundle_correct(
    session_id: str,
    message: str,
    authenticated_user_id: str,
) -> AsyncGenerator[dict, None]:
    """Handle bundle_correct action — apply NL corrections to last generated bundle.

    Yields SSE event dicts. Returns None if should fall through to normal chat.
    """
    if session_id not in _last_bundle:
        return

    try:
        prev = _last_bundle[session_id]
        prev_bundle_id = prev["bundle_id"]
        prev_srs_text = prev["srs_text"]

        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.PROGRESS.value,
                "content": f"Applying correction to bundle `{prev_bundle_id[:8]}`...",
                "metadata": {"progress": {"step": "Applying correction", "current": 1, "total": 3}},
            }),
        }

        from app.routers.bundle import _parse_srs_text, _run_generation, _extract_json_from_response, BUNDLE_CORRECTION_SYSTEM_PROMPT
        from app.services.bundle_generator import get_bundle_status, get_bundle_file_tree
        from app.models.schemas import BundleStatusType, SRSData

        # Use stored SRSData if available (from XLSX upload), else re-parse text
        stored_srs = prev.get("srs_data")
        if stored_srs:
            original_srs_data = stored_srs
        else:
            original_srs_data = await _parse_srs_text(prev_srs_text)
        srs_dict = original_srs_data.model_dump()

        # Build a summary of current state for the LLM to preserve
        orig_form_names = [f.get("name", "?") for f in srs_dict.get("forms", [])]
        orig_programs = [p.get("name", p) if isinstance(p, dict) else p for p in srs_dict.get("programs", [])]
        orig_encounters = srs_dict.get("encounterTypes", [])

        # Use LLM to apply the correction
        correction_prompt = (
            f"Current SRS data:\n```json\n{json.dumps(srs_dict, indent=2)}\n```\n\n"
            f"CURRENT STATE SUMMARY (you MUST preserve unless explicitly asked to change):\n"
            f"- {len(orig_form_names)} forms: {orig_form_names}\n"
            f"- {len(orig_programs)} programs: {orig_programs}\n"
            f"- {len(orig_encounters)} encounter types: {orig_encounters}\n\n"
            f"User's correction:\n{message}\n\n"
            f"Apply ONLY this correction. Return the modified SRS JSON with ALL {len(orig_form_names)} forms preserved."
        )
        corrected_json_str = await claude_client.complete(
            messages=[{"role": "user", "content": correction_prompt}],
            system_prompt=BUNDLE_CORRECTION_SYSTEM_PROMPT,
        )
        modified_srs = _extract_json_from_response(corrected_json_str)
        if not modified_srs:
            raise ValueError("LLM did not return valid JSON for correction")

        correction_notes = modified_srs.pop("_correction_notes", None)

        # Post-correction validation: check LLM didn't drop forms
        new_form_names = [f.get("name", "?") for f in modified_srs.get("forms", [])]
        dropped_forms = set(orig_form_names) - set(new_form_names)
        if dropped_forms:
            logger.warning(
                "LLM correction dropped %d forms: %s — restoring them",
                len(dropped_forms), dropped_forms,
            )
            # Restore dropped forms from original
            existing_names = {f.get("name") for f in modified_srs.get("forms", [])}
            for orig_form in srs_dict.get("forms", []):
                if orig_form.get("name") in dropped_forms and orig_form.get("name") not in existing_names:
                    modified_srs["forms"].append(orig_form)
                    existing_names.add(orig_form.get("name"))
            if correction_notes:
                correction_notes += f" | Restored {len(dropped_forms)} dropped form(s): {dropped_forms}"
            else:
                correction_notes = f"Restored {len(dropped_forms)} dropped form(s): {dropped_forms}"

        corrected_srs = SRSData(**modified_srs)

        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.PROGRESS.value,
                "content": "Correction applied. Regenerating bundle...",
                "metadata": {"progress": {"step": "Regenerating bundle", "current": 2, "total": 3}},
            }),
        }

        new_bundle_id = str(uuid.uuid4())
        await _run_generation(corrected_srs, new_bundle_id)

        status = get_bundle_status(new_bundle_id)
        if status and status.status == BundleStatusType.COMPLETED:
            file_tree = get_bundle_file_tree(new_bundle_id)
            _last_bundle[session_id] = {
                "bundle_id": new_bundle_id,
                "srs_text": prev_srs_text + f"\n\nCorrection: {message}",
                "srs_data": corrected_srs,  # Store for chained corrections
            }

            notes_text = f"\n\n**Correction notes:** {correction_notes}" if correction_notes else ""
            summary = (
                f"Bundle regenerated with your correction applied!{notes_text}\n\n"
                f"**New Bundle ID:** `{new_bundle_id[:8]}`\n"
                f"You can download the updated ZIP or browse the files below.\n\n"
                f"Need more changes? Just tell me what to fix."
            )
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": summary,
                }),
            }
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "bundle_ready",
                    "content": "",
                    "metadata": {
                        "bundleId": new_bundle_id,
                        "downloadUrl": f"/api/bundle/{new_bundle_id}/download",
                        "files": file_tree,
                    },
                }),
            }
            await save_message(session_id, "assistant", summary, user_id=authenticated_user_id)
        else:
            error_msg = status.error if status else "Unknown error"
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": f"Bundle regeneration failed: {error_msg}\n\nPlease try again.",
                }),
            }
            await save_message(session_id, "assistant", f"Bundle regeneration failed: {error_msg}", user_id=authenticated_user_id)

        yield {
            "event": "message",
            "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
        }

    except Exception as e:
        logger.exception("Bundle correction from chat failed")
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": f"Correction failed: {str(e)}\n\nLet me help you describe the change differently.\n\n",
            }),
        }
        # Caller should fall through to normal LLM chat


async def handle_pending_modelling(
    session_id: str,
    message: str,
    authenticated_user_id: str,
) -> tuple[Any | None, bool]:
    """Handle awaiting_modelling state — user provides programs/encounters.

    Returns (parsed_xlsx_srs or None, completed).
    If completed=True, caller should proceed with _parsed_xlsx_srs for generation.
    If completed=False and parsed_xlsx_srs is None, the handler yielded a retry message.
    """
    pending = _bundle_pending.get(session_id, {})
    if not pending.get("awaiting_modelling"):
        return None, False

    pending = _bundle_pending.pop(session_id)
    stored_srs = pending.get("srs_data")

    if not stored_srs:
        return None, False

    # Use LLM to extract modelling from user's text message
    modelling_prompt = (
        f"The user provided modelling information for an Avni implementation.\n\n"
        f"User's message:\n{message}\n\n"
        f"Existing forms: {[f.name for f in stored_srs.forms]}\n\n"
        f"Extract and return a JSON object with:\n"
        f'{{"programs": [{{"name": "..."}}], '
        f'"encounter_types": [{{"name": "...", "program": "..."}}], '
        f'"forms": [{{"sheet_name": "...", "form_type": "...", "program": "...", "encounter_type": "..."}}]}}\n\n'
        f"Map each form to the correct program and encounter type based on the user's modelling."
    )
    from app.services.llm_sheet_extractor import _parse_llm_json, apply_llm_modelling, CLASSIFICATION_SYSTEM_PROMPT
    modelling_json_str = await claude_client.complete(
        messages=[{"role": "user", "content": modelling_prompt}],
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
    )
    modelling = _parse_llm_json(modelling_json_str)

    if modelling and (modelling.get("programs") or modelling.get("encounter_types")):
        parsed_xlsx_srs = apply_llm_modelling(stored_srs, modelling)
        return parsed_xlsx_srs, True
    else:
        # LLM couldn't parse modelling from text — ask again
        _bundle_pending[session_id] = pending
        _bundle_pending[session_id]["awaiting_modelling"] = True
        return None, False


def get_modelling_retry_events() -> list[dict]:
    """Return SSE events for modelling retry prompt."""
    return [
        {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": "I couldn't extract the modelling from that. Please specify clearly:\n\n"
                           "- **Programs:** e.g., Pregnancy, Child, Nutrition\n"
                           "- **Encounters per program:** e.g., ANC -> Pregnancy, Growth Monitoring -> Child\n",
            }),
        },
        {
            "event": "message",
            "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
        },
    ]


async def handle_bundle_create_pending(
    session_id: str,
    message: str,
    authenticated_user_id: str,
) -> AsyncGenerator[dict, None]:
    """Handle bundle creation when user has answered pending clarification questions.

    Yields SSE event dicts.
    """
    pending = _bundle_pending.pop(session_id)
    original_srs = pending.get("srs_text", "")

    yield {
        "event": "message",
        "data": json.dumps({
            "type": SSEEventType.PROGRESS.value,
            "content": "Great! Generating bundle with your clarifications...",
            "metadata": {"progress": {"step": "Generating bundle", "current": 1, "total": 3}},
        }),
    }

    # Combine original SRS with user's clarification answers
    history = await get_history(session_id, limit=20)
    clarification_context = "\n".join(
        f"{m['role']}: {m['content']}" for m in history[-6:]
    )
    enriched_srs = (
        f"{original_srs}\n\n"
        f"--- Additional clarifications from user ---\n"
        f"{clarification_context}\n"
        f"User's latest answer: {message}"
    )

    from app.routers.bundle import _parse_srs_text, _run_generation
    from app.services.bundle_generator import get_bundle_status, get_bundle_file_tree
    from app.models.schemas import BundleStatusType

    yield {
        "event": "message",
        "data": json.dumps({
            "type": SSEEventType.TEXT.value,
            "content": "Parsing your requirements and generating the implementation bundle...\n\n",
        }),
    }

    srs_data = await _parse_srs_text(enriched_srs)
    bundle_id = str(uuid.uuid4())

    yield {
        "event": "message",
        "data": json.dumps({
            "type": SSEEventType.PROGRESS.value,
            "content": f"Parsed SRS: {len(srs_data.forms)} forms, "
                       f"{len(srs_data.subjectTypes)} subject types. "
                       f"Generating bundle...",
            "metadata": {"progress": {"step": "Generating bundle", "current": 2, "total": 3}},
        }),
    }

    await _run_generation(srs_data, bundle_id)

    status = get_bundle_status(bundle_id)
    if status and status.status == BundleStatusType.COMPLETED:
        file_tree = get_bundle_file_tree(bundle_id)
        _last_bundle[session_id] = {"bundle_id": bundle_id, "srs_text": enriched_srs}
        summary = (
            f"Bundle generated successfully! {status.message}\n\n"
            f"**Bundle ID:** `{bundle_id[:8]}`\n"
            f"You can download the ZIP or browse the files below.\n\n"
            f"If anything looks wrong, just tell me what to change — e.g., "
            f"*\"change ANC frequency to monthly\"* or *\"add a weight field to the registration form\"*."
        )
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": summary,
            }),
        }
        yield {
            "event": "message",
            "data": json.dumps({
                "type": "bundle_ready",
                "content": "",
                "metadata": {
                    "bundleId": bundle_id,
                    "downloadUrl": f"/api/bundle/{bundle_id}/download",
                    "files": file_tree,
                },
            }),
        }
        await save_message(session_id, "assistant", summary, user_id=authenticated_user_id)
    else:
        error_msg = status.error if status else "Unknown error"
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": f"Bundle generation failed: {error_msg}\n\n"
                           "Please check your program description and try again.",
            }),
        }
        await save_message(session_id, "assistant", f"Bundle generation failed: {error_msg}", user_id=authenticated_user_id)

    yield {
        "event": "message",
        "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
    }


async def run_clarification_pipeline(
    message: str,
    org_name: str | None,
    sector: str | None,
) -> list[str]:
    """Run the clarification pipeline (ClarityEngine + LLM) for SRS content.

    Returns a list of clarification questions/messages, or empty if none needed.
    """
    clarifications: list[str] = []
    try:
        from app.services.document_extractor import (
            generate_clarifications,
            map_to_avni_domain,
            structure_content,
        )
        from app.services.clarity_engine import clarity_engine

        requirements = await structure_content(message)
        org_label = org_name or "Organisation"
        mapped_srs = await map_to_avni_domain(requirements, org_name=org_label)

        # Layer 1: Deterministic structural gap detection (fast, no LLM)
        srs_dict = mapped_srs.model_dump()
        _org_ctx = {"org_name": org_name, "sector": sector} if org_name else None
        clarity_questions = await clarity_engine.analyze(srs_dict, org_context=_org_ctx)

        # Use the clarity engine's formatted output for critical/important questions
        if clarity_questions:
            _clarity_chat_msg = clarity_engine.format_for_chat(clarity_questions)
            if _clarity_chat_msg:
                clarifications = [_clarity_chat_msg]

        # Layer 2: LLM-based clarification for nuanced gaps (additive)
        if not clarity_questions or all(
            q.severity.value == "nice" for q in clarity_questions
        ):
            cq_list = await generate_clarifications(requirements, mapped_srs)
            llm_clarifications = [q.question for q in cq_list if q.question]
            if llm_clarifications and not clarifications:
                clarifications = llm_clarifications

    except Exception as e:
        logger.warning("Clarification generation failed (non-fatal): %s", e)

    return clarifications


async def generate_bundle_direct(
    message: str,
    session_id: str,
    authenticated_user_id: str,
) -> AsyncGenerator[dict, None]:
    """Generate a bundle directly from SRS text (no clarification needed).

    Yields SSE event dicts.
    """
    yield {
        "event": "message",
        "data": json.dumps({
            "type": SSEEventType.TEXT.value,
            "content": (
                "I'll generate an Avni implementation bundle from your description. "
                "Parsing and structuring the data...\n\n"
                "**Tip:** For best results, use our [SRS Template](/api/bundle/srs-template?format=xlsx) "
                "(XLSX) — it maps 1:1 to Avni's data model and produces 100% correct bundles "
                "with rules, skip logic, and visit schedules.\n\n"
            ),
        }),
    }

    from app.routers.bundle import _parse_srs_text, _run_generation
    from app.services.bundle_generator import get_bundle_status, get_bundle_file_tree
    from app.models.schemas import BundleStatusType

    srs_data = await _parse_srs_text(message)
    bundle_id = str(uuid.uuid4())

    yield {
        "event": "message",
        "data": json.dumps({
            "type": SSEEventType.PROGRESS.value,
            "content": f"Parsed SRS: {len(srs_data.forms)} forms, "
                       f"{len(srs_data.subjectTypes)} subject types. "
                       f"Generating bundle...",
            "metadata": {"progress": {"step": "Generating bundle", "current": 2, "total": 3}},
        }),
    }

    await _run_generation(srs_data, bundle_id)

    status = get_bundle_status(bundle_id)
    if status and status.status == BundleStatusType.COMPLETED:
        file_tree = get_bundle_file_tree(bundle_id)
        _last_bundle[session_id] = {"bundle_id": bundle_id, "srs_text": message}
        summary = (
            f"Bundle generated successfully! {status.message}\n\n"
            f"**Bundle ID:** `{bundle_id[:8]}`\n"
            f"You can download the ZIP or browse the files below.\n\n"
            f"If anything looks wrong, just tell me what to change — e.g., "
            f"*\"change ANC frequency to monthly\"* or *\"add a weight field to the registration form\"*."
        )
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": summary,
            }),
        }
        yield {
            "event": "message",
            "data": json.dumps({
                "type": "bundle_ready",
                "content": "",
                "metadata": {
                    "bundleId": bundle_id,
                    "downloadUrl": f"/api/bundle/{bundle_id}/download",
                    "files": file_tree,
                },
            }),
        }
        await save_message(session_id, "assistant", summary, user_id=authenticated_user_id)
    else:
        error_msg = status.error if status else "Unknown error"
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": f"Bundle generation failed: {error_msg}\n\n"
                           "Please check your program description and try again. "
                           "Make sure to include subject types, programs, encounter types, and form fields.",
            }),
        }
        await save_message(session_id, "assistant", f"Bundle generation failed: {error_msg}", user_id=authenticated_user_id)

    yield {
        "event": "message",
        "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
    }


async def process_file_attachments(
    attachments: list,
    session_id: str,
) -> tuple[str, Any]:
    """Process CSV/XLSX file attachments.

    Returns (attachment_context_text, parsed_xlsx_srs or None).
    Also yields SSE events via the returned generator-compatible structure.
    """
    # This is complex enough that it's handled inline in chat_handler
    # to preserve the yield-based SSE streaming pattern.
    # See chat_handler.py _process_attachments_inline() for the implementation.
    pass


async def generate_bundle_from_xlsx(
    parsed_xlsx_srs: Any,
    attachment_context: str,
    session_id: str,
    authenticated_user_id: str,
) -> AsyncGenerator[dict, None]:
    """Generate a bundle directly from parsed XLSX SRS data.

    Yields SSE event dicts.
    """
    from app.routers.bundle import _run_generation
    from app.services.bundle_generator import get_bundle_status, get_bundle_file_tree
    from app.models.schemas import BundleStatusType

    bundle_id = str(uuid.uuid4())
    form_count = len(parsed_xlsx_srs.forms)
    field_count = sum(
        len([field for g in form.groups for field in g.fields])
        for form in parsed_xlsx_srs.forms
    )
    program_names = [p.get("name", p) if isinstance(p, dict) else p for p in parsed_xlsx_srs.programs]
    et_names = list(parsed_xlsx_srs.encounterTypes)
    form_names = [f.name for f in parsed_xlsx_srs.forms]

    # Build workflow steps for UI
    workflow_id = f"bundle-{bundle_id[:8]}"
    workflow_steps = [
        {"id": "parse", "name": "Parse SRS", "description": "Extract forms and fields from uploaded file", "status": "completed",
         "resultSummary": f"{form_count} forms, {field_count} fields"},
        {"id": "subject-types", "name": "Subject Types", "description": "Generate subject types", "status": "running",
         "resultSummary": f"{len(parsed_xlsx_srs.subjectTypes)} types"},
        {"id": "programs", "name": "Programs", "description": "Generate programs", "status": "pending",
         "resultSummary": f"{len(program_names)}: {', '.join(program_names)}" if program_names else "none"},
        {"id": "encounters", "name": "Encounter Types", "description": "Generate encounter types", "status": "pending",
         "resultSummary": f"{len(et_names)}: {', '.join(et_names)}" if et_names else "none"},
        {"id": "concepts", "name": "Concepts & Forms", "description": "Generate concepts and forms", "status": "pending",
         "resultSummary": f"{form_count} forms"},
        {"id": "mappings", "name": "Form Mappings", "description": "Link forms to subject types & programs", "status": "pending"},
        {"id": "privileges", "name": "Groups & Privileges", "description": "Generate access control", "status": "pending"},
        {"id": "validate", "name": "Validate Bundle", "description": "Check against Avni server contracts", "status": "pending"},
        {"id": "zip", "name": "Create ZIP", "description": "Package bundle for upload", "status": "pending"},
    ]

    yield {
        "event": "message",
        "data": json.dumps({
            "type": "workflow_progress",
            "content": f"Generating bundle from {form_count} forms, {field_count} fields...",
            "metadata": {
                "workflowId": workflow_id,
                "workflowName": f"Bundle Generation",
                "workflowSteps": workflow_steps,
                "workflowCurrentStep": 1,
                "workflowStatus": "running",
                "workflowDetail": f"Forms: {', '.join(form_names[:5])}{'...' if len(form_names) > 5 else ''}",
            },
        }),
    }

    # Cache parsed SRS for review wizard
    from app.services.cache import cache_parsed_srs
    await cache_parsed_srs(bundle_id, parsed_xlsx_srs)

    await _run_generation(parsed_xlsx_srs, bundle_id)

    status = get_bundle_status(bundle_id)
    if status and status.status == BundleStatusType.COMPLETED:
        file_tree = get_bundle_file_tree(bundle_id)
        _last_bundle[session_id] = {
            "bundle_id": bundle_id,
            "srs_text": attachment_context,
            "srs_data": parsed_xlsx_srs,  # Store structured data for corrections
        }

        # Mark all workflow steps as completed
        for step in workflow_steps:
            step["status"] = "completed"
        yield {
            "event": "message",
            "data": json.dumps({
                "type": "workflow_progress",
                "content": "",
                "metadata": {
                    "workflowId": workflow_id,
                    "workflowName": "Bundle Generation",
                    "workflowSteps": workflow_steps,
                    "workflowCurrentStep": len(workflow_steps) - 1,
                    "workflowStatus": "completed",
                },
            }),
        }

        summary = (
            f"Bundle generated successfully! {status.message}\n\n"
            f"**Bundle ID:** `{bundle_id[:8]}`\n"
            f"You can download the ZIP or browse the files below.\n\n"
            f"If anything looks wrong, just tell me what to change — e.g., "
            f"*\"change ANC frequency to monthly\"* or *\"add a weight field to the registration form\"*."
        )
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": summary,
            }),
        }
        yield {
            "event": "message",
            "data": json.dumps({
                "type": "bundle_ready",
                "content": "",
                "metadata": {
                    "bundleId": bundle_id,
                    "downloadUrl": f"/api/bundle/{bundle_id}/download",
                    "files": file_tree,
                },
            }),
        }
        await save_message(session_id, "assistant", summary, user_id=authenticated_user_id)
    else:
        error_msg = status.error if status else "Unknown error"
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.TEXT.value,
                "content": f"Bundle generation failed: {error_msg}\n\n"
                           "Please check your scoping sheet format and try again.",
            }),
        }
        await save_message(session_id, "assistant", f"Bundle generation failed: {error_msg}", user_id=authenticated_user_id)

    yield {
        "event": "message",
        "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
    }
