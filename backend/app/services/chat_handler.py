"""Main chat orchestration — coordinates intent routing, action detection,
SSE streaming, and response generation.

This is the core handler called by the chat router endpoint.
"""
import json
import logging
import re
import uuid
from typing import Any, AsyncGenerator

from app import db
from app.config import settings
from app.models.schemas import (
    Attachment,
    IntentType,
    SSEEventType,
)
from app.services.claude_client import claude_client
from app.services.intent_router import classify_intent
from app.services.output_guard import guard_output, OutputGuardResult
from app.services.rag.fallback import rag_service

from app.services.action_detector import detect_action
from app.services.context_manager import (
    _bundle_pending,
    _last_bundle,
    _pending_actions,
    get_org_context,
    set_org_context,
    get_history,
    save_message,
    get_srs_state,
    update_srs_state,
    get_srs_phase,
    set_srs_phase,
)
from app.services.intent_handler import (
    handle_bundle_regenerate,
    handle_bundle_correct,
    handle_pending_modelling,
    get_modelling_retry_events,
    handle_bundle_create_pending,
    run_clarification_pipeline,
    generate_bundle_direct,
    generate_bundle_from_xlsx,
)
from app.services.prompt_builder import build_system_prompt
from app.services.srs_parser import parse_multiple_srs_excels

logger = logging.getLogger(__name__)

# Skill routing: intent -> relevant skill names for focused retrieval
SKILL_FOR_INTENT: dict[IntentType, list[str]] = {
    IntentType.BUNDLE: ["srs-bundle-generator", "avni-implementor", "project-scoping"],
    IntentType.RULE: ["avni-rules-debugger", "implementation-engineer", "product-codebase"],
    IntentType.SUPPORT: ["support-engineer", "support-patterns", "avni-server-debugger"],
    IntentType.CONFIG: ["org-setup", "field-implementation", "avni-implementor"],
    IntentType.KNOWLEDGE: ["product-knowledge", "backend-architecture", "architecture-patterns"],
    IntentType.VOICE: ["avni-client", "mobile-testing"],
    IntentType.IMAGE: ["avni-client"],
    IntentType.CHAT: [],
}


async def _get_skill_context(intent: IntentType, message: str) -> str:
    """Retrieve relevant skill knowledge for the detected intent."""
    skill_names = SKILL_FOR_INTENT.get(intent, [])
    if not skill_names:
        return ""

    try:
        skill_results = await rag_service.search(
            query=message,
            collection="skills",
            top_k=5,
        )
        if not skill_results:
            return ""

        relevant = []
        for r in skill_results:
            skill_name = r.metadata.get("skill", "")
            if any(s in skill_name.lower() for s in [n.lower() for n in skill_names]):
                relevant.append(r)
            elif r.score > 0.5:
                relevant.append(r)

        if not relevant:
            relevant = skill_results[:3]

        parts = []
        for r in relevant[:4]:
            skill = r.metadata.get("skill", "unknown")
            parts.append(f"[skill:{skill}] {r.text[:600]}")
        return "\n".join(parts)
    except Exception:
        return ""


async def _build_knowledge_context(intent: IntentType, message: str) -> str:
    """Build reference context from the full knowledge base (32K+ chunks)
    plus skill-aware retrieval and PageIndex tree-based document retrieval."""
    results = []

    # Layer 1: Vector + keyword hybrid search (32K+ chunks)
    try:
        results = await rag_service.search_all(message, limit=10)
    except Exception:
        pass

    # Layer 1b: Intent-specific focused search
    try:
        if intent == IntentType.RULE:
            rule_results = await rag_service.search_rules(message, limit=5)
            results.extend(rule_results)
        elif intent == IntentType.SUPPORT:
            support_results = await rag_service.search_tickets(message, limit=5)
            results.extend(support_results)
        elif intent in (IntentType.BUNDLE, IntentType.CONFIG):
            concept_results = await rag_service.search_concepts(message, limit=5)
            results.extend(concept_results)
    except Exception:
        pass

    # Layer 1c: Skill-aware knowledge (from avni-skills corpus)
    skill_context = await _get_skill_context(intent, message)

    # Layer 2: PageIndex tree-based reasoning retrieval (indexed documents)
    pageindex_sections = []
    try:
        from app.services.pageindex_service import pageindex_service
        if pageindex_service._initialized and pageindex_service._pool:
            pageindex_sections = await pageindex_service.retrieve(
                query=message,
                max_sections=3,
            )
    except Exception:
        pass

    if not results and not pageindex_sections and not skill_context:
        return ""

    # Deduplicate vector results by content prefix
    seen = set()
    unique_results = []
    for r in results:
        key = r.text[:100]
        if key not in seen:
            seen.add(key)
            unique_results.append(r)

    context_parts = []

    for r in unique_results[:12]:
        context_parts.append(f"[{r.category}] {r.text[:500]}")

    if skill_context:
        context_parts.append(f"\n--- Skill Knowledge ---\n{skill_context}")

    for section in pageindex_sections:
        text = section.get("text", "")
        if text:
            doc = section.get("document", "document")
            title = section.get("title", "")
            context_parts.append(f"[document:{doc}:{title}] {text[:800]}")

    return "\n".join(context_parts)


async def handle_chat_message(
    *,
    message: str,
    effective_message: str,
    session_id: str,
    authenticated_user_id: str,
    attachments: list[Attachment] | None,
    org_name: str | None,
    sector: str | None,
    org_context_text: str | None,
    user_org_id: str,
    action: str | None,
    intent: IntentType,
    intent_result: Any,
    guardrail_warnings: list[str],
    filter_result: Any,
    byok_provider: str | None = None,
    byok_api_key: str | None = None,
) -> AsyncGenerator[dict, None]:
    """Main chat orchestration generator. Yields SSE event dicts.

    This is the core logic extracted from the chat endpoint's event_generator().
    """
    # Initialize variables used across multiple code paths
    _parsed_xlsx_srs = None
    clarification_questions: list[str] = []

    try:
        # Send intent classification
        progress_msg = f"Intent: {intent.value} (confidence: {intent_result.confidence:.2f})"
        if action:
            progress_msg += f" | Action: {action}"
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.PROGRESS.value,
                "content": progress_msg,
            }),
        }

        # ── Bundle regeneration — fix errors in last generated bundle ──
        if action == "bundle_regenerate" and session_id in _last_bundle:
            completed = False
            async for event in handle_bundle_regenerate(session_id, message, authenticated_user_id):
                yield event
                if json.loads(event["data"]).get("type") == SSEEventType.DONE.value:
                    completed = True
            if completed:
                return
            # If not completed (exception path), fall through to normal LLM chat

        # ── Bundle correction — apply NL corrections to last generated bundle ──
        if action == "bundle_correct" and session_id in _last_bundle:
            completed = False
            async for event in handle_bundle_correct(session_id, message, authenticated_user_id):
                yield event
                if json.loads(event["data"]).get("type") == SSEEventType.DONE.value:
                    completed = True
            if completed:
                return
            # Fall through to normal LLM chat

        # ── LLM-based intent routing for bundle workflows ──────────────
        # Instead of 200 lines of regex, we ask the LLM what to do.
        # Falls back to safe heuristics if LLM call fails.
        from app.services.llm_router import route_bundle_intent

        _has_file_attachments = bool(attachments and any(
            (att.filename or "").lower().endswith(('.xlsx', '.xls', '.csv', '.tsv'))
            for att in attachments
        ))
        _has_stored_srs = bool(
            session_id in _bundle_pending
            and _bundle_pending[session_id].get("srs_data")
        )
        _has_pending_text = bool(
            session_id in _bundle_pending
            and _bundle_pending[session_id].get("questions_asked")
            and not _bundle_pending[session_id].get("srs_data")
        )
        _is_bundle_context = (
            _has_file_attachments
            or _has_stored_srs
            or _has_pending_text
            or action == "bundle_create"
        )

        # Handle awaiting_modelling separately (user needs to provide program mapping)
        _awaiting_modelling = (
            session_id in _bundle_pending
            and _bundle_pending[session_id].get("awaiting_modelling")
        )
        if _awaiting_modelling:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.PROGRESS.value,
                    "content": "Applying modelling to your forms...",
                    "metadata": {"progress": {"step": "Applying modelling", "current": 1, "total": 3}},
                }),
            }
            parsed_xlsx_srs, modelling_ok = await handle_pending_modelling(
                session_id, message, authenticated_user_id,
            )
            if not modelling_ok and parsed_xlsx_srs is None:
                for event in get_modelling_retry_events():
                    yield event
                return
            elif modelling_ok and parsed_xlsx_srs is not None:
                _parsed_xlsx_srs = parsed_xlsx_srs
                _has_stored_srs = True
                _is_bundle_context = True

        # Route via LLM if we're in a bundle context
        _routed_action = None
        if _is_bundle_context and not _awaiting_modelling:
            _routed = await route_bundle_intent(
                message=message,
                has_file_attachments=_has_file_attachments,
                has_stored_srs=_has_stored_srs,
                has_pending_text=_has_pending_text,
            )
            _routed_action = _routed["action"]
            logger.info("LLM router decided: %s (%s)", _routed_action, _routed.get("reason", ""))

        # ── Execute the routed action ──

        if _routed_action == "ask_clarification":
            # No files, no stored SRS — ask what the user needs
            _bundle_pending[session_id] = {
                "srs_text": message,
                "questions_asked": True,
            }
            clarification_questions = [
                "What is the name of your program? (e.g., Maternal Health, Nutrition, TB)",
                "What type of beneficiaries will you track? (e.g., Individual, Household, Group)",
                "What are the main visit types or encounters? (e.g., ANC visits, Home visits, Follow-ups)",
                "What information do you need to collect during registration? (e.g., name, age, gender, address, phone)",
                "Are there any specific forms or visits that should repeat on a schedule? (e.g., monthly ANC visits)",
            ]
            # Fall through to LLM chat which will include these questions

        elif _routed_action == "generate_bundle" and _has_stored_srs:
            # User confirmed — generate from stored SRS
            stored = _bundle_pending.pop(session_id, {})
            _parsed_xlsx_srs = stored.get("srs_data", _parsed_xlsx_srs)
            if _parsed_xlsx_srs and len(_parsed_xlsx_srs.forms) > 0:
                try:
                    async for event in generate_bundle_from_xlsx(
                        _parsed_xlsx_srs, "", session_id, authenticated_user_id,
                    ):
                        yield event
                    return
                except Exception as e:
                    logger.exception("Confirmed XLSX bundle generation failed")

        elif _routed_action == "generate_bundle" and _has_pending_text:
            # User confirmed text-based bundle
            try:
                async for event in handle_bundle_create_pending(session_id, message, authenticated_user_id):
                    yield event
                return
            except Exception as e:
                logger.exception("Text bundle generation failed")
                _bundle_pending.pop(session_id, None)

        elif _routed_action == "apply_correction" and _has_stored_srs:
            # Deterministic correction — LLM classifies command, code applies it
            from app.services.srs_corrections import classify_correction, apply_correction as apply_srs_correction

            stored_srs = _bundle_pending[session_id].get("srs_data")
            if stored_srs:
                cmd = await classify_correction(message, stored_srs)
                logger.info("Correction command: %s (entity=%s)", cmd.command, cmd.entity)

                if cmd.command != "unknown":
                    corrected_srs, description = apply_srs_correction(stored_srs, cmd)
                    # Update stored SRS
                    _bundle_pending[session_id]["srs_data"] = corrected_srs
                    _parsed_xlsx_srs = corrected_srs  # triggers show_summary below
                    _routed_action = "show_summary"  # re-show updated summary

                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": SSEEventType.TEXT.value,
                            "content": f"Done: {description}\n\n",
                        }),
                    }
                    # Fall through to show_summary which will display updated modelling
                else:
                    # Unknown command — fall through to LLM chat for help
                    _bundle_pending[session_id]["srs_text"] = (
                        _bundle_pending[session_id].get("srs_text", "")
                        + f"\n\nUser correction: {message}"
                    )
                    clarification_questions = []
                    # Fall through to LLM chat

        # ── File attachment processing ────────────────────────────────
        attachment_context = ""
        _pending_modelling = None
        _xlsx_attachments = []
        if attachments:
            for att in attachments:
                fname = att.filename or ""
                if fname.lower().endswith(('.csv', '.tsv')):
                    try:
                        import base64
                        raw = base64.b64decode(att.data).decode("utf-8", errors="ignore")
                        lines = raw.strip().split("\n")
                        preview = "\n".join(lines[:100])
                        total = len(lines) - 1
                        attachment_context += (
                            f"\n\n--- Uploaded File: {fname} ({total} rows) ---\n"
                            f"{preview}\n"
                            f"{'... (truncated, showing first 100 rows)' if total > 99 else ''}\n"
                        )
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "type": SSEEventType.TEXT.value,
                                "content": f"I've loaded **{fname}** ({total} rows). ",
                            }),
                        }
                    except Exception as e:
                        logger.warning("Failed to parse CSV attachment %s: %s", fname, e)
                elif fname.lower().endswith(('.xlsx', '.xls')):
                    # Collect xlsx files for batch processing below
                    _xlsx_attachments.append(att)

            # ── Batch XLSX processing: deterministic parser first ─────────
            if _xlsx_attachments:
                import base64, tempfile, os
                from app.services.llm_sheet_extractor import (
                    extract_modelling_mechanical, apply_mechanical_modelling,
                    parse_xlsx_with_llm,
                )

                # Step 1: Write all xlsx files to temp paths
                tmp_paths = []
                xlsx_fnames = []
                for att in _xlsx_attachments:
                    fname = att.filename or "unknown.xlsx"
                    xlsx_fnames.append(fname)
                    raw = base64.b64decode(att.data)
                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(fname)[1]) as tmp:
                        tmp.write(raw)
                        tmp_paths.append(tmp.name)

                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": SSEEventType.PROGRESS.value,
                        "content": f"Analyzing {len(tmp_paths)} Excel file(s)...",
                    }),
                }

                # Step 1b: Check if any file is a canonical template — if so, use deterministic parser
                from app.services.canonical_srs_parser import is_canonical_template as _is_canonical, parse_canonical_srs as _parse_canonical
                _canonical_srs = None
                for i, tmp_path in enumerate(tmp_paths):
                    if _is_canonical(tmp_path):
                        logger.info("Detected canonical SRS template: %s", xlsx_fnames[i])
                        _canonical_srs, _canonical_errors = _parse_canonical(tmp_path)
                        if _canonical_errors:
                            error_list = "\n".join(f"- {e}" for e in _canonical_errors[:10])
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "type": SSEEventType.TEXT.value,
                                    "content": (
                                        f"Detected **canonical SRS template** in {xlsx_fnames[i]}. "
                                        f"Found {len(_canonical_errors)} issue(s):\n\n{error_list}\n\n"
                                        f"Please fix these in the template and re-upload."
                                    ),
                                }),
                            }
                        if _canonical_srs and len(_canonical_srs.forms) > 0:
                            srs_data = _canonical_srs
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "type": SSEEventType.TEXT.value,
                                    "content": (
                                        f"Parsed **canonical template**: {len(srs_data.forms)} forms, "
                                        f"{sum(len(f) for form in srs_data.forms for f in [[field for g in form.groups for field in g.fields]])} fields "
                                        f"(deterministic parser, zero LLM). "
                                    ),
                                }),
                            }
                            # Skip heuristic + LLM parsers entirely
                            break

                if _canonical_srs and len(_canonical_srs.forms) > 0:
                    # Canonical path — skip all heuristic/LLM parsing
                    _parsed_xlsx_srs = _canonical_srs
                    _pending_modelling = None

                    form_count = len(srs_data.forms)
                    field_count = sum(len(f) for form in srs_data.forms for f in [
                        [field for g in form.groups for field in g.fields]
                    ])
                    all_fnames = ", ".join(xlsx_fnames)
                    attachment_context += (
                        f"\n\n--- Canonical SRS Template: {all_fnames} ---\n"
                        f"Forms ({form_count}): {[f.name for f in srs_data.forms]}\n"
                        f"Total fields: {field_count}\n"
                    )
                else:
                    _canonical_srs = None  # Non-canonical path continues below

                _skip_heuristic = _canonical_srs is not None and len(getattr(_canonical_srs, 'forms', [])) > 0

                # Steps 2-6: Heuristic + LLM parsing (SKIPPED for canonical templates)
                if _skip_heuristic:
                    srs_data = _canonical_srs

                # Step 2: Extract mechanical modelling from ALL files
                if not _skip_heuristic:
                    for i, tmp_path in enumerate(tmp_paths):
                        mechanical_modelling = extract_modelling_mechanical(tmp_path)
                        if mechanical_modelling:
                            _pending_modelling = mechanical_modelling
                            logger.info(
                                "Extracted mechanical modelling from %s: %d subject types, %d programs, %d encounters",
                                xlsx_fnames[i],
                                len(mechanical_modelling.get("subject_types", [])),
                                len(mechanical_modelling.get("programs", [])),
                                len(mechanical_modelling.get("encounters", [])),
                            )

                # Steps 3-5: Heuristic + LLM parsing (skipped for canonical templates)
                if not _skip_heuristic:
                    # Step 3: Use deterministic parser (primary)
                    srs_data = None
                    try:
                        srs_data = parse_multiple_srs_excels(tmp_paths)
                        if srs_data and len(srs_data.forms) > 0:
                            logger.info(
                                "Deterministic parser returned %d forms from %d file(s)",
                                len(srs_data.forms), len(tmp_paths),
                            )
                        else:
                            logger.info("Deterministic parser returned 0 forms, falling back to LLM parser")
                            srs_data = None
                    except Exception as e:
                        logger.warning("Deterministic parser failed: %s — falling back to LLM parser", e)
                        srs_data = None

                    # Step 4: Fall back to LLM parser only if deterministic parser failed
                    if srs_data is None or len(srs_data.forms) == 0:
                        for i, tmp_path in enumerate(tmp_paths):
                            try:
                                llm_srs = await parse_xlsx_with_llm(tmp_path)
                                if llm_srs and len(llm_srs.forms) > 0:
                                    if srs_data is None or len(srs_data.forms) == 0:
                                        srs_data = llm_srs
                                    elif len(llm_srs.forms) > len(srs_data.forms):
                                        srs_data = llm_srs
                            except Exception as e:
                                logger.warning("LLM parser failed for %s: %s", xlsx_fnames[i], e)

                    # Step 5: Apply mechanical modelling enrichment
                    if srs_data and len(srs_data.forms) > 0 and _pending_modelling:
                        logger.info("Applying mechanical modelling to %d forms", len(srs_data.forms))
                        srs_data = apply_mechanical_modelling(srs_data, _pending_modelling)

                # Step 6: Clean up temp files
                for tmp_path in tmp_paths:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

                if srs_data and len(srs_data.forms) > 0:
                    # If awaiting modelling from a previous upload, merge
                    _awaiting_modelling_file = session_id in _bundle_pending and _bundle_pending[session_id].get("awaiting_modelling")
                    if _awaiting_modelling_file:
                        stored_srs = _bundle_pending.pop(session_id, {}).get("srs_data")
                        if stored_srs:
                            if _pending_modelling:
                                srs_data = apply_mechanical_modelling(stored_srs, _pending_modelling)
                            elif srs_data.programs:
                                from app.services.llm_sheet_extractor import apply_llm_modelling
                                modelling_dict = {
                                    "org_name": srs_data.orgName,
                                    "programs": srs_data.programs,
                                    "encounter_types": srs_data.encounterTypes,
                                    "forms": [
                                        {"sheet_name": f.name, "form_type": f.formType,
                                         "program": f.programName, "encounter_type": f.encounterTypeName,
                                         "in_scope": True}
                                        for f in srs_data.forms
                                    ],
                                }
                                srs_data = apply_llm_modelling(stored_srs, modelling_dict)

                    _parsed_xlsx_srs = srs_data

                    # Summarize parsed data
                    form_count = len(srs_data.forms)
                    field_count = sum(len(f) for form in srs_data.forms for f in [
                        [field for g in form.groups for field in g.fields]
                    ])
                    all_fnames = ", ".join(xlsx_fnames)
                    attachment_context += (
                        f"\n\n--- Uploaded SRS Excel(s): {all_fnames} ---\n"
                        f"Organisation: {srs_data.orgName}\n"
                        f"Programs: {[p.get('name', p) if isinstance(p, dict) else str(p) for p in srs_data.programs]}\n"
                        f"Subject Types: {[st.get('name', '') if isinstance(st, dict) else str(st) for st in srs_data.subjectTypes]}\n"
                        f"Encounter Types: {srs_data.encounterTypes}\n"
                        f"Forms ({form_count}): {[f.name for f in srs_data.forms]}\n"
                        f"Total fields: {field_count}\n"
                    )
                    for form in srs_data.forms[:5]:
                        fields_list = [f"{field.name} ({field.dataType})" for g in form.groups for field in g.fields[:10]]
                        attachment_context += f"\n  Form '{form.name}' ({form.formType}): {fields_list}\n"

                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": SSEEventType.TEXT.value,
                            "content": f"I've parsed **{all_fnames}**: {form_count} forms, {field_count} fields. ",
                        }),
                    }
                else:
                    all_fnames = ", ".join(xlsx_fnames)
                    logger.warning("All parsers failed for Excel files: %s", all_fnames)
                    attachment_context += f"\n\n--- Uploaded Excel(s): {all_fnames} (parse failed) ---\n"

        # ── Check for missing modelling in parsed XLSX ──
        _modelling_missing = False
        if _parsed_xlsx_srs and _has_file_attachments and len(_parsed_xlsx_srs.forms) > 0:
            has_programs = bool(_parsed_xlsx_srs.programs and len(_parsed_xlsx_srs.programs) > 0)
            has_encounters = bool(_parsed_xlsx_srs.encounterTypes and len(_parsed_xlsx_srs.encounterTypes) > 0)
            has_program_forms = any(
                f.formType in ("ProgramEnrolment", "ProgramEncounter", "ProgramExit")
                for f in _parsed_xlsx_srs.forms
            )
            if has_program_forms and not has_programs:
                _modelling_missing = True
            elif not has_programs and not has_encounters:
                all_registration = all(f.formType == "IndividualProfile" for f in _parsed_xlsx_srs.forms)
                if not all_registration:
                    _modelling_missing = True

        if _modelling_missing and _parsed_xlsx_srs:
            _bundle_pending[session_id] = {
                "srs_data": _parsed_xlsx_srs,
                "questions_asked": True,
                "awaiting_modelling": True,
            }
            form_names = [f.name for f in _parsed_xlsx_srs.forms[:10]]
            missing_msg = (
                f"I parsed **{len(_parsed_xlsx_srs.forms)} forms** from your file, but I couldn't determine the **modelling** "
                f"(which programs, encounter types, and how forms map to them).\n\n"
                f"**Forms found:** {', '.join(form_names)}"
                f"{'...' if len(_parsed_xlsx_srs.forms) > 10 else ''}\n\n"
                f"Please either:\n"
                f"1. **Upload a modelling sheet** (Excel with programs, encounter types, form-program mapping)\n"
                f"2. **Tell me the modelling** — e.g., *\"Programs: Pregnancy, Child. "
                f"Encounters: ANC (Pregnancy), PNC (Pregnancy), Growth Monitoring (Child)\"*\n\n"
                f"Once I have the modelling, I'll generate the complete bundle."
            )
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": missing_msg,
                }),
            }
            await save_message(session_id, "assistant", missing_msg, user_id=authenticated_user_id)
            yield {
                "event": "message",
                "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
            }
            return

        # ── After XLSX parsing: LLM router already decided "show_summary" ──
        # Always show parsed summary and ask for confirmation on fresh uploads.
        if _routed_action == "show_summary" and _parsed_xlsx_srs and len(_parsed_xlsx_srs.forms) > 0:
            # Run clarity engine — only show CRITICAL blockers in review flow
            # (user already sees the modelling table for non-critical issues)
            try:
                from app.services.clarity_engine import clarity_engine as _ce
                _xlsx_srs_dict = _parsed_xlsx_srs.model_dump()
                _xlsx_org_ctx = {"org_name": org_name, "sector": sector} if org_name else None
                _xlsx_clarity_qs = await _ce.analyze(_xlsx_srs_dict, org_context=_xlsx_org_ctx)
                _xlsx_critical = [q for q in _xlsx_clarity_qs if q.severity.value == "critical"]
                if _xlsx_critical:
                    # Only format critical questions — skip important/nice to avoid overwhelming
                    clarity_msg = _ce.format_for_chat(_xlsx_critical, max_questions=5)
                    if clarity_msg:
                        clarification_questions = [clarity_msg]
            except Exception as _ce_err:
                logger.debug("XLSX clarity engine check skipped: %s", _ce_err)

            # Store SRS and show summary
            _bundle_pending[session_id] = {
                "srs_data": _parsed_xlsx_srs,
                "srs_text": attachment_context,
                "questions_asked": True,
            }
            form_count = len(_parsed_xlsx_srs.forms)
            field_count = sum(
                len(field)
                for form in _parsed_xlsx_srs.forms
                for field in [[f for g in form.groups for f in g.fields]]
            )
            programs = [p.get("name", p) if isinstance(p, dict) else str(p) for p in _parsed_xlsx_srs.programs]
            ets = _parsed_xlsx_srs.encounterTypes
            sts = [st.get("name", "") if isinstance(st, dict) else str(st) for st in _parsed_xlsx_srs.subjectTypes]

            # Build modelling table (mirrors canonical template format)
            modelling_rows: list[str] = []
            for st in _parsed_xlsx_srs.subjectTypes:
                st_name = st.get("name", "Individual") if isinstance(st, dict) else str(st)
                st_type = st.get("type", "Person") if isinstance(st, dict) else "Person"
                reg_form = next(
                    (f for f in _parsed_xlsx_srs.forms
                     if f.formType == "IndividualProfile"
                     and (f.subjectTypeName == st_name or not f.subjectTypeName)),
                    None,
                )
                form_name = reg_form.name if reg_form else "—"
                modelling_rows.append(f"| SubjectType | {st_name} | {st_type} | {form_name} | IndividualProfile |")

            for prog in _parsed_xlsx_srs.programs:
                p_name = prog.get("name", prog) if isinstance(prog, dict) else str(prog)
                enrol_form = next(
                    (f for f in _parsed_xlsx_srs.forms if f.formType == "ProgramEnrolment" and f.programName == p_name),
                    None,
                )
                form_name = enrol_form.name if enrol_form else "—"
                modelling_rows.append(f"| Program | {p_name} | | {form_name} | ProgramEnrolment |")

            for form in _parsed_xlsx_srs.forms:
                if form.formType in ("ProgramEncounter", "Encounter"):
                    et_name = form.encounterTypeName or form.name
                    parent = form.programName or ""
                    modelling_rows.append(f"| EncounterType | {et_name} | {parent} | {form.name} | {form.formType} |")

            modelling_table = "\n".join(modelling_rows)

            review_msg = (
                f"Here's what I parsed from your SRS (**{form_count} forms, {field_count} fields**):\n\n"
                f"**Modelling:**\n"
                f"| Entity Type | Name | Parent | Form Name | Form Type |\n"
                f"|---|---|---|---|---|\n"
                f"{modelling_table}\n\n"
                f"**Forms detail:**\n"
            )
            for form in _parsed_xlsx_srs.forms:
                fields = [f for g in form.groups for f in g.fields]
                review_msg += (
                    f"- **{form.name}** ({form.formType})"
                    f"{' → ' + form.programName if form.programName else ''}"
                    f" — {len(fields)} fields\n"
                )

            # Determine if this came from canonical template (100% accurate) or heuristic (needs review)
            _was_canonical = locals().get('_skip_heuristic', False)

            if clarification_questions:
                review_msg += f"\n{clarification_questions[0]}"
            elif _was_canonical:
                # Canonical template — high confidence, generate is safe
                review_msg += (
                    f"\nParsed from **canonical template** (deterministic, zero guessing).\n"
                    f"- Reply **\"generate\"** to create the bundle\n"
                    f"- Or tell me what to change"
                )
            else:
                # Heuristic/LLM parse — names may be wrong, template download is the safe path
                review_msg += (
                    f"\n**Note:** I parsed this from a free-form SRS, so entity names and form types may not be accurate "
                    f"(e.g., sheet names used as program names).\n\n"
                    f"**Recommended — review & fix in Excel (2 min):**\n"
                    f"1. [Download the pre-filled SRS Template](/api/bundle/srs-review/{session_id}/template)\n"
                    f"2. Open in Excel → check the **Modelling** sheet → fix any wrong names/types\n"
                    f"3. Re-upload the corrected file → get a **100% correct** bundle\n\n"
                    f"Or reply **\"generate as-is\"** to create the bundle from the table above (may have issues)."
                )

            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": review_msg,
                }),
            }
            await save_message(session_id, "assistant", review_msg, user_id=authenticated_user_id)
            yield {
                "event": "message",
                "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
            }
            return

        # Build knowledge context (includes skill-aware retrieval)
        knowledge_context = await _build_knowledge_context(intent, message)

        # Load conversation history from DB
        history = await get_history(session_id, limit=20)
        llm_messages = [{"role": m["role"], "content": m["content"]} for m in history]

        # Build system prompt
        full_system = build_system_prompt(
            org_name=org_name,
            sector=sector,
            org_context_text=org_context_text,
            knowledge_context=knowledge_context,
            intent=intent,
            action=action,
            attachment_context=attachment_context,
            clarification_questions=clarification_questions,
            is_pending_bundle=session_id in _bundle_pending,
            skip_bundle_block=False,
            session_id=session_id,
        )

        # ── SRS Builder Mode ──────────────────────────────────────────
        # If this session has an active SRS building state, augment the
        # system prompt with SRS builder context and phase instructions.
        srs_state = get_srs_state(session_id)
        is_srs_mode = srs_state is not None

        if is_srs_mode:
            from app.routers.srs_chat import (
                SRS_CHAT_BUILDER_CORE_PROMPT,
                _PHASE_PROMPTS,
                _build_srs_context_summary,
            )
            srs_phase = get_srs_phase(session_id)
            phase_hint = _PHASE_PROMPTS.get(srs_phase, "")
            srs_summary = _build_srs_context_summary(srs_state)

            # Prepend SRS context to the existing system prompt
            srs_system = (
                f"{SRS_CHAT_BUILDER_CORE_PROMPT}\n\n"
                f"## Current Phase: {srs_phase}\n{phase_hint}\n\n"
                f"## Current SRS State:\n{srs_summary}"
            )
            full_system = srs_system + "\n\n" + full_system

        # Stream the response
        full_response = ""
        async for chunk in claude_client.stream_chat(
            messages=llm_messages,
            system_prompt=full_system,
            byok_provider=byok_provider,
            byok_api_key=byok_api_key,
        ):
            full_response += chunk
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.TEXT.value,
                    "content": chunk,
                }),
            }

        # ── Output Guardrails ──
        output_guard_result: OutputGuardResult = guard_output(
            text=full_response,
            rag_confidence=None,
            org_id=user_org_id,
        )

        # Log guardrail events
        if output_guard_result.modifications:
            if output_guard_result.system_prompt_leaked:
                await db.log_guardrail_event(
                    event_type="system_prompt_leak",
                    details={"modifications": output_guard_result.modifications},
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )
            if output_guard_result.script_injection_found:
                await db.log_guardrail_event(
                    event_type="script_injection",
                    details={"modifications": output_guard_result.modifications},
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )
            if output_guard_result.low_confidence_warning:
                await db.log_guardrail_event(
                    event_type="low_confidence",
                    details={"modifications": output_guard_result.modifications},
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )
            if output_guard_result.gender_bias_fixed:
                await db.log_guardrail_event(
                    event_type="gender_bias_fixed",
                    details={
                        "substitutions": output_guard_result.gender_bias_substitutions,
                        "stage": "output",
                        "action": "fix",
                    },
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )
            if output_guard_result.ban_list_triggered:
                await db.log_guardrail_event(
                    event_type="ban_list_triggered",
                    details={
                        "banned_words": [b["word"] for b in output_guard_result.banned_words_found],
                        "stage": "output",
                        "action": "fix",
                        "org_id": user_org_id,
                    },
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )
            if output_guard_result.pii_redacted_in_output:
                await db.log_guardrail_event(
                    event_type="pii_redacted",
                    details={
                        "stage": "output",
                        "action": "fix",
                    },
                    session_id=session_id,
                    user_id=authenticated_user_id,
                )

        # Use sanitized response for persistence
        final_response = output_guard_result.sanitized_text
        await save_message(session_id, "assistant", final_response, user_id=authenticated_user_id)

        # ── SRS extraction (post-stream) ──────────────────────────────
        if is_srs_mode:
            try:
                from app.routers.srs_chat import (
                    _extract_srs_update,
                    _validate_srs_update,
                    _determine_next_phase,
                )
                srs_update = await _extract_srs_update(full_response, srs_state, srs_phase)
                if srs_update:
                    validated = _validate_srs_update(srs_update)
                    if validated:
                        update_srs_state(session_id, validated)
                        yield {
                            "event": "message",
                            "data": json.dumps({"type": "srs_update", "data": validated}),
                        }
                        # Check phase advancement
                        next_phase = _determine_next_phase(srs_phase, full_response, validated)
                        if next_phase and next_phase != srs_phase:
                            set_srs_phase(session_id, next_phase)
                            yield {
                                "event": "message",
                                "data": json.dumps({"type": "phase", "phase": next_phase}),
                            }
            except Exception as e:
                logger.warning("SRS extraction failed: %s", e)

        # Send guardrail metadata to frontend
        all_guardrail_warnings = guardrail_warnings + output_guard_result.modifications
        if all_guardrail_warnings:
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": "guardrail_info",
                    "content": "",
                    "metadata": {
                        "warnings": all_guardrail_warnings,
                        "input_filter": filter_result.to_dict(),
                        "output_guard": output_guard_result.to_dict(),
                    },
                }),
            }

        # Send action metadata if detected
        if action:
            action_id = str(uuid.uuid4())[:12]
            pending = {
                "action_id": action_id,
                "session_id": session_id,
                "action_type": action,
                "details": {
                    "org_context": get_org_context(session_id),
                },
            }
            _pending_actions[action_id] = pending

            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.CONFIRM_ACTION.value,
                    "content": json.dumps({
                        "action_id": action_id,
                        "action_type": action,
                        "description": f"The AI wants to perform: {action.replace('_', ' ')}",
                        "requires_approval": True,
                    }),
                }),
            }

        yield {
            "event": "message",
            "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
        }

    except Exception as e:
        logger.exception("Chat streaming error for session %s", session_id)
        yield {
            "event": "message",
            "data": json.dumps({
                "type": SSEEventType.ERROR.value,
                "content": f"An error occurred: {str(e)}",
            }),
        }
