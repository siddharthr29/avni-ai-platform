"""SRS Builder chat endpoints — context-aware AI assistance for SRS editing.

Provides:
1. POST /srs/chat — Tab-aware SRS assistant (original)
2. POST /srs/mode — Activate/deactivate SRS builder mode on a chat session
3. GET /srs/state/{session_id} — Get current SRS state for a session

SRS builder mode works by augmenting the main /api/chat endpoint rather than
running a separate chat system. When active, the chat handler prepends SRS
builder context to the system prompt and runs structured extraction after
each response.
"""

import json
import logging
import time
from collections import defaultdict

from fastapi import APIRouter
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app.models.schemas import SSEEventType
from app.services.claude_client import claude_client
from app.services.rag.fallback import rag_service

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# In-memory conversation store (keyed by session_id, max 20 messages each)
# ---------------------------------------------------------------------------
_conversation_store: dict[str, list[dict]] = defaultdict(list)
_MAX_HISTORY = 20

# ---------------------------------------------------------------------------
# Original SRS Chat (tab-based) — unchanged
# ---------------------------------------------------------------------------

SRS_SYSTEM_PROMPT = """You are an expert Avni implementation consultant embedded in the SRS (Scoping & Requirement Specification) Builder.

You help program managers create complete, production-ready SRS documents for Avni — the open-source platform used by Indian NGOs for field data collection.

Your deep knowledge covers:
- All Avni entity types: SubjectTypes, Programs, EncounterTypes, Forms, Concepts, FormMappings, Groups, Privileges
- SRS structure: 8 tabs (Summary, Programs, Users, W3H, Forms, Visit Scheduling, Dashboard Cards, Permissions)
- Sector-specific patterns: MCH, WASH, Education, Nutrition, Livelihoods, TB, NCD, Sports
- Form design: data types (Text, Numeric, Coded, Date, Notes, Image, PhoneNumber), skip logic, validations
- Visit scheduling: frequencies, conditions, overdue windows, cancellation handling
- Production patterns from 50+ real Avni implementations

Rules:
- Give concise, actionable suggestions tailored to the current tab being edited.
- When suggesting form fields, include data type, options (for Coded), and skip logic where appropriate.
- When suggesting programs, include encounter types and enrollment criteria.
- Use Indian NGO context (ASHA, ANM, AWW, SHG, Block/District hierarchies).
- Never hallucinate specific concept UUIDs or form JSONs unless asked.
- If the user mentions a sector, suggest sector-specific patterns.
"""

TAB_CONTEXT = {
    "summary": "The user is filling the Program Summary tab: organization name, location, hierarchy, previous system, challenges, timeline, number of users, data migration needs.",
    "programs": "The user is defining Programs: program names, objectives, eligibility criteria, entry/exit points, beneficiary counts, success indicators, required forms and reports.",
    "users": "The user is defining User Personas: field worker types (ANM, ASHA, Supervisor), descriptions, and counts.",
    "w3h": "The user is filling the W3H (What/When/Who/How) tab: mapping activities to schedules, responsible persons, and data collection methods (Mobile/Web/Both).",
    "forms": "The user is designing Forms: form names, field definitions with data types, mandatory flags, coded options, skip logic, numeric ranges, and page grouping.",
    "visitScheduling": "The user is configuring Visit Scheduling: trigger events, form schedules, frequencies, conditions, overdue windows, cancellation handling.",
    "dashboardCards": "The user is defining Dashboard Cards: card names, filter logic, and target user types for offline dashboards.",
    "permissions": "The user is setting up the Permission Matrix: which user groups can view/register/edit/void which forms and entities.",
}


class SRSChatRequest(BaseModel):
    message: str
    session_id: str
    current_tab: str = "summary"
    srs_context: dict | None = None
    org_name: str | None = None
    sector: str | None = None


@router.post("/srs/chat")
async def srs_chat(request: SRSChatRequest) -> EventSourceResponse:
    """SRS-specific chat endpoint with tab context awareness."""
    message = request.message
    current_tab = request.current_tab
    srs_context = request.srs_context
    org_name = request.org_name
    sector = request.sector

    async def event_generator():
        try:
            # Build system prompt with tab context
            system_parts = [SRS_SYSTEM_PROMPT]

            # Tab context
            tab_hint = TAB_CONTEXT.get(current_tab, "")
            if tab_hint:
                system_parts.append(f"\n\nCURRENT TAB: {current_tab}\n{tab_hint}")

            # Organization context
            if org_name or sector:
                org_lines = ["\n\n--- Organization Context ---"]
                if org_name:
                    org_lines.append(f"Organization: {org_name}")
                if sector:
                    org_lines.append(f"Sector: {sector}")
                system_parts.append("\n".join(org_lines))

            # SRS data context (summarized to avoid token bloat)
            if srs_context:
                summary_parts = ["\n\n--- Current SRS Data ---"]
                if srs_context.get("summary"):
                    s = srs_context["summary"]
                    if s.get("organizationName"):
                        summary_parts.append(f"Org: {s['organizationName']}")
                    if s.get("location"):
                        summary_parts.append(f"Location: {s['location']}")
                if srs_context.get("programs"):
                    prog_names = [p.get("name", "") for p in srs_context["programs"] if p.get("name")]
                    if prog_names:
                        summary_parts.append(f"Programs: {', '.join(prog_names)}")
                if srs_context.get("users"):
                    user_types = [u.get("type", "") for u in srs_context["users"] if u.get("type")]
                    if user_types:
                        summary_parts.append(f"User types: {', '.join(user_types)}")
                if srs_context.get("forms"):
                    form_names = [f.get("name", "") for f in srs_context["forms"] if f.get("name")]
                    if form_names:
                        summary_parts.append(f"Forms: {', '.join(form_names)}")
                system_parts.append("\n".join(summary_parts))

            # RAG knowledge context
            try:
                rag_results = await rag_service.search(message, top_k=5)
                if rag_results:
                    knowledge_parts = [
                        "\n\n--- Reference Knowledge ---",
                        "Use this to inform your answers but present it as your own expertise:",
                    ]
                    for r in rag_results:
                        knowledge_parts.append(f"- {r.text[:300]}")
                    system_parts.append("\n".join(knowledge_parts))
            except Exception:
                pass  # RAG failure shouldn't block chat

            full_system = "".join(system_parts)

            # Stream the response
            full_response = ""
            async for chunk in claude_client.stream_chat(
                messages=[{"role": "user", "content": message}],
                system_prompt=full_system,
            ):
                full_response += chunk
                yield {
                    "event": "message",
                    "data": json.dumps({
                        "type": SSEEventType.TEXT.value,
                        "content": chunk,
                    }),
                }

            yield {
                "event": "message",
                "data": json.dumps({"type": SSEEventType.DONE.value, "content": ""}),
            }

        except Exception as e:
            logger.exception("SRS chat error for session %s", request.session_id)
            yield {
                "event": "message",
                "data": json.dumps({
                    "type": SSEEventType.ERROR.value,
                    "content": f"Error: {str(e)}",
                }),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# Chat-based SRS Builder — two-call approach (stream text + extract structured)
# ---------------------------------------------------------------------------

CONVERSATION_PHASES = [
    "start", "org", "subjects", "programs", "encounters",
    "forms", "scheduling", "dashboard", "review",
]

# Session eviction for memory management
_session_last_active: dict[str, float] = {}
_SESSION_TTL = 1800  # 30 minutes


def _cleanup_sessions() -> None:
    """Evict sessions inactive for 30+ minutes."""
    now = time.time()
    expired = [sid for sid, ts in _session_last_active.items() if now - ts > _SESSION_TTL]
    for sid in expired:
        _conversation_store.pop(sid, None)
        _session_last_active.pop(sid, None)
    if expired:
        logger.info("Evicted %d stale SRS chat-builder sessions", len(expired))


# ---------------------------------------------------------------------------
# Simplified system prompt — core + phase-specific additions
# ---------------------------------------------------------------------------

SRS_CHAT_BUILDER_CORE_PROMPT = """You are an Avni implementation consultant helping build an SRS (Software Requirements Specification) through conversation.

## Avni Data Model
- SubjectType: Who you track (Individual/Person, Household, Group)
- Program: Longitudinal tracking (e.g., Maternal Health, Child Nutrition)
- EncounterType: Visits within a program (e.g., ANC Visit, Growth Monitoring)
- Forms: Data collection (Registration, Enrolment, Visit, Exit, Cancellation)

## Form Types
- IndividualProfile: Subject registration form
- ProgramEnrolment: Enrolling into a program (needs programName)
- ProgramExit: Exiting a program (needs programName)
- ProgramEncounter: Visit within a program (needs programName + encounterTypeName)
- ProgramEncounterCancellation: Cancelling a program visit
- Encounter: Standalone visit not under any program (needs encounterTypeName)
- IndividualEncounterCancellation: Cancelling a standalone visit

## Data Types
Text, Numeric (with unit/ranges), Coded (SingleSelect/MultiSelect with options array), Date, DateTime, Notes, PhoneNumber, Image, Location, Duration, QuestionGroup

## Your Role
Ask clear questions to understand the user's implementation needs. Be specific about:
- Program names and what they track
- Encounter types and their frequency
- Form fields with proper data types
- For Coded fields: always list the options
- For Numeric fields: mention unit and expected range
- Visit scheduling: how often, what triggers it, overdue window

## Conversation Style
- Ask 2-3 focused questions at a time
- Suggest sector-appropriate defaults (don't make the user specify everything)
- Confirm understanding before moving on
- Use Indian NGO context (ASHA, ANM, AWW roles; State/District/Block hierarchy)

## Important
- Every program needs: enrolment form, exit form, and at least one encounter form
- Every encounter type needs a cancellation form (auto-generated)
- Registration forms collect demographics; enrolment forms collect program-specific baseline
- Include "Everyone" in user groups
- Higher level number = larger geography (State=3 > District=2 > Block=1)
- Coded fields MUST include options and type (SingleSelect/MultiSelect)
- Numeric fields: include unit, lowAbsolute, highAbsolute where applicable
- Set mandatory=true for key identifiers (name, age, gender, phone)"""


_PHASE_PROMPTS = {
    "start": "Start by asking the organization name and sector (MCH, Nutrition, Education, Livelihoods, WASH, or other).",
    "org": "Ask about geography (which states/districts), location hierarchy levels, and any existing data systems.",
    "subjects": "Ask who they track. Most orgs track Individuals. Some also track Households, Groups (SHGs), or Facilities.",
    "programs": "Ask what programs they run. For MCH: Maternal Health, Child Health, Family Planning. For Nutrition: Child Nutrition, SAM/MAM Management. Suggest standard programs for their sector.",
    "encounters": "Ask what visits/interactions happen in each program. For each encounter: what's it called, how often, who does it. Distinguish program encounters (under a program) from general encounters (standalone).",
    "forms": "For each form, ask what fields to capture. Suggest standard fields based on the sector. Be specific about data types and options. Group fields by page/section.",
    "scheduling": "Ask about visit frequencies. For each encounter type: how many days between visits, when is it overdue. Common: ANC monthly (30d due, 45d overdue), PNC at day 1/3/7/42.",
    "dashboard": "Ask what indicators they need. Suggest: total registered, due visits, overdue visits, high-risk cases, recent registrations.",
    "review": "Summarize everything built. Ask if anything needs to change. Mention they can generate the bundle when ready.",
}


# ---------------------------------------------------------------------------
# SRS extraction prompt — used for the second (structured) LLM call
# ---------------------------------------------------------------------------

SRS_EXTRACTION_PROMPT = """You are a JSON extractor. Given a conversation about building an Avni SRS, extract any NEW or CHANGED SRS data mentioned.

Return ONLY a JSON object with the fields that were discussed or changed. Use this exact schema:

{
  "orgName": "string or null",
  "subjectTypes": [{"name": "string", "type": "Person|Household|Group"}] or null,
  "programs": [{"name": "string", "colour": "#hex"}] or null,
  "encounterTypes": ["string"] or null,
  "generalEncounterTypes": ["string"] or null,
  "programEncounterMappings": [{"program": "string", "encounterTypes": ["string"]}] or null,
  "forms": [{
    "name": "string",
    "formType": "IndividualProfile|ProgramEnrolment|ProgramExit|ProgramEncounter|ProgramEncounterCancellation|Encounter|IndividualEncounterCancellation",
    "programName": "string or null",
    "encounterTypeName": "string or null",
    "subjectTypeName": "string or null",
    "groups": [{
      "name": "string",
      "fields": [{
        "name": "string",
        "dataType": "Text|Numeric|Coded|Date|DateTime|Notes|PhoneNumber|Image|Location|Duration|QuestionGroup",
        "mandatory": true/false,
        "options": ["string"] or null,
        "type": "SingleSelect|MultiSelect" or null,
        "unit": "string or null",
        "lowAbsolute": number or null,
        "highAbsolute": number or null,
        "lowNormal": number or null,
        "highNormal": number or null,
        "keyValues": [{"key": "string", "value": "any"}] or null
      }]
    }]
  }] or null,
  "groups": ["string"] or null,
  "addressLevelTypes": [{"name": "string", "level": number, "parent": "string or null"}] or null,
  "visitSchedules": [{"trigger": "string", "schedule_encounter": "string", "due_days": number, "overdue_days": number}] or null,
  "eligibilityRules": [{"program": "string", "condition": "string"}] or null
}

Rules:
- Return ONLY fields that were NEW or CHANGED in this conversation turn. Omit unchanged fields.
- Use null for the entire field if it wasn't discussed.
- For arrays: return the COMPLETE list for that field (all items, not just new ones).
- Ensure all data types are valid Avni types.
- For Coded fields, always include options array.
- For encounter types, include both program encounters AND their cancellation forms.
- Include exit forms for any new programs.
- Return ONLY valid JSON. No markdown, no explanation."""


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

VALID_DATA_TYPES = {
    "Text", "Numeric", "Coded", "Date", "DateTime", "Time", "Notes",
    "PhoneNumber", "Image", "ImageV2", "File", "Video", "Audio",
    "Location", "Duration", "QuestionGroup", "Id", "Subject", "NA",
}

VALID_FORM_TYPES = {
    "IndividualProfile", "ProgramEnrolment", "ProgramExit",
    "ProgramEncounter", "ProgramEncounterCancellation",
    "Encounter", "IndividualEncounterCancellation",
}


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class SRSChatBuilderRequest(BaseModel):
    message: str
    session_id: str
    current_srs: dict | None = None
    conversation_phase: str = "start"


# ---------------------------------------------------------------------------
# Helper: build system prompt with phase context
# ---------------------------------------------------------------------------

def _build_system_prompt(phase: str, current_srs: dict | None) -> str:
    """Build focused system prompt with only current-phase context."""
    parts = [SRS_CHAT_BUILDER_CORE_PROMPT]

    # Phase-specific instruction
    phase_hint = _PHASE_PROMPTS.get(phase, "")
    if phase_hint:
        parts.append(f"\n\n## Current Phase: {phase.upper()}\n{phase_hint}")

    # Current SRS state
    srs_summary = _build_srs_context_summary(current_srs or {})
    if srs_summary:
        parts.append(srs_summary)

    return "\n".join(parts)


def _build_srs_context_summary(srs: dict) -> str:
    """Summarize current SRS state for inclusion in the system prompt."""
    if not srs:
        return ""

    parts = ["--- CURRENT SRS STATE (built so far) ---"]

    if srs.get("orgName") and srs["orgName"] != "Organisation":
        parts.append(f"Organization: {srs['orgName']}")
    if srs.get("sector"):
        parts.append(f"Sector: {srs['sector']}")

    if srs.get("addressLevelTypes"):
        levels = [a.get("name", "") for a in srs["addressLevelTypes"]]
        parts.append(f"Address hierarchy: {' > '.join(levels)}")

    if srs.get("subjectTypes"):
        names = [s.get("name", "") for s in srs["subjectTypes"] if s.get("name")]
        if names:
            parts.append(f"Subject types: {', '.join(names)}")

    if srs.get("programs"):
        names = [p.get("name", "") for p in srs["programs"] if p.get("name")]
        if names:
            parts.append(f"Programs: {', '.join(names)}")

    if srs.get("encounterTypes"):
        parts.append(f"Encounter types: {', '.join(srs['encounterTypes'][:15])}")

    if srs.get("forms"):
        form_info = []
        for f in srs["forms"]:
            fname = f.get("name", "?")
            ftype = f.get("formType", "?")
            nfields = sum(len(g.get("fields", [])) for g in f.get("groups", []))
            form_info.append(f"{fname} ({ftype}, {nfields} fields)")
        parts.append(f"Forms: {'; '.join(form_info[:10])}")

    if srs.get("visitSchedules"):
        parts.append(f"Visit schedules: {len(srs['visitSchedules'])} defined")

    if srs.get("programEncounterMappings"):
        for m in srs["programEncounterMappings"]:
            prog = m.get("program", "?")
            encs = m.get("encounterTypes", [])
            parts.append(f"  {prog} encounters: {', '.join(encs)}")

    if len(parts) == 1:
        return ""  # Nothing built yet

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helper: conversation history management
# ---------------------------------------------------------------------------

def _save_to_history(session_id: str, role: str, content: str, srs_summary: str = "") -> None:
    """Save a message to conversation history with optional SRS context annotation."""
    store = _conversation_store[session_id]
    entry_content = content
    if role == "assistant" and srs_summary:
        entry_content = f"{content}\n\n[SRS changes applied: {srs_summary}]"
    store.append({"role": role, "content": entry_content})
    # Keep first 2 messages (initial context) + last 18 for long conversations
    if len(store) > _MAX_HISTORY:
        _conversation_store[session_id] = store[:2] + store[-(_MAX_HISTORY - 2):]


def _build_messages(session_id: str, new_message: str) -> list[dict]:
    """Build the messages list from conversation history plus the new user message."""
    messages = []
    for msg in _conversation_store[session_id]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    return messages


# ---------------------------------------------------------------------------
# Helper: extract structured SRS update (second LLM call)
# ---------------------------------------------------------------------------

async def _extract_srs_update(
    assistant_text: str,
    current_srs: dict | None,
    phase: str,
) -> dict | None:
    """Extract structured SRS update from assistant's response using a separate LLM call."""
    # Only extract if we're past the start phase (start is just greeting)
    if phase == "start":
        return None

    srs_summary = _build_srs_context_summary(current_srs or {})
    if not srs_summary:
        srs_summary = "No SRS built yet."

    extraction_prompt = (
        f"Current SRS state:\n{srs_summary}\n\n"
        f"Assistant's response to user:\n{assistant_text}\n\n"
        f"Extract any NEW or CHANGED SRS data from the assistant's response. "
        f"If nothing new was discussed, return {{}}"
    )

    try:
        result = await claude_client.complete(
            messages=[{"role": "user", "content": extraction_prompt}],
            system_prompt=SRS_EXTRACTION_PROMPT,
            task_type="srs_parsing",
        )

        # Clean and parse JSON — handle markdown code fences
        cleaned = result.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (with optional language tag)
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        data = json.loads(cleaned)

        # Remove null/None values — only keep actual updates
        return {k: v for k, v in data.items() if v is not None} or None

    except json.JSONDecodeError as e:
        logger.warning("SRS extraction: JSON parse failed: %s", e)
        return None
    except Exception as e:
        logger.warning("SRS extraction: call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Helper: validate SRS update against Avni schema
# ---------------------------------------------------------------------------

def _validate_srs_update(update: dict) -> dict | None:
    """Validate and clean an SRS update. Returns cleaned update or None."""
    if not update or not isinstance(update, dict):
        return None

    cleaned: dict = {}

    # Validate string fields
    for key in ("orgName",):
        if key in update and isinstance(update[key], str):
            val = update[key].strip()
            if val:
                cleaned[key] = val

    # Validate subjectTypes
    if "subjectTypes" in update and isinstance(update["subjectTypes"], list):
        valid_subject_types = {"Person", "Individual", "Household", "Group", "User"}
        valid = [
            st for st in update["subjectTypes"]
            if isinstance(st, dict) and st.get("name") and st.get("type") in valid_subject_types
        ]
        if valid:
            cleaned["subjectTypes"] = valid

    # Validate programs
    if "programs" in update and isinstance(update["programs"], list):
        valid = [p for p in update["programs"] if isinstance(p, dict) and p.get("name")]
        if valid:
            cleaned["programs"] = valid

    # Validate simple string lists
    for key in ("encounterTypes", "generalEncounterTypes", "groups"):
        if key in update and isinstance(update[key], list):
            valid = [s for s in update[key] if isinstance(s, str) and s.strip()]
            if valid:
                cleaned[key] = valid

    # Validate forms
    if "forms" in update and isinstance(update["forms"], list):
        valid_forms = []
        for form in update["forms"]:
            if not isinstance(form, dict) or not form.get("name"):
                continue
            if form.get("formType") and form["formType"] not in VALID_FORM_TYPES:
                logger.warning("Dropping form '%s': invalid formType '%s'", form.get("name"), form["formType"])
                continue
            # Validate fields within groups
            if "groups" in form and isinstance(form["groups"], list):
                for group in form["groups"]:
                    if "fields" in group and isinstance(group["fields"], list):
                        for field in group["fields"]:
                            if field.get("dataType") and field["dataType"] not in VALID_DATA_TYPES:
                                original = field["dataType"]
                                field["dataType"] = "Text"
                                logger.warning(
                                    "Field '%s': invalid dataType '%s', defaulting to Text",
                                    field.get("name"), original,
                                )
            valid_forms.append(form)
        if valid_forms:
            cleaned["forms"] = valid_forms

    # Validate addressLevelTypes
    if "addressLevelTypes" in update and isinstance(update["addressLevelTypes"], list):
        valid = [
            alt for alt in update["addressLevelTypes"]
            if isinstance(alt, dict) and alt.get("name") and isinstance(alt.get("level"), (int, float))
        ]
        if valid:
            cleaned["addressLevelTypes"] = valid

    # Validate programEncounterMappings
    if "programEncounterMappings" in update and isinstance(update["programEncounterMappings"], list):
        valid = [
            m for m in update["programEncounterMappings"]
            if isinstance(m, dict) and m.get("program") and isinstance(m.get("encounterTypes"), list)
        ]
        if valid:
            cleaned["programEncounterMappings"] = valid

    # Validate visitSchedules
    if "visitSchedules" in update and isinstance(update["visitSchedules"], list):
        valid = [
            vs for vs in update["visitSchedules"]
            if isinstance(vs, dict) and vs.get("trigger") and vs.get("schedule_encounter")
        ]
        if valid:
            cleaned["visitSchedules"] = valid

    # Validate eligibilityRules
    if "eligibilityRules" in update and isinstance(update["eligibilityRules"], list):
        valid = [
            er for er in update["eligibilityRules"]
            if isinstance(er, dict) and er.get("program") and er.get("condition")
        ]
        if valid:
            cleaned["eligibilityRules"] = valid

    return cleaned if cleaned else None


# ---------------------------------------------------------------------------
# Helper: phase advancement logic
# ---------------------------------------------------------------------------

def _determine_next_phase(current_phase: str, assistant_text: str, srs_update: dict | None) -> str | None:
    """Determine if the conversation should advance to the next phase."""
    if not srs_update:
        return None

    phase_order = [
        "start", "org", "subjects", "programs", "encounters",
        "forms", "scheduling", "dashboard", "review",
    ]

    # Auto-advance based on what data was emitted
    phase_triggers = {
        "start": lambda u: "orgName" in u,
        "org": lambda u: "subjectTypes" in u,
        "subjects": lambda u: "programs" in u,
        "programs": lambda u: "encounterTypes" in u,
        "encounters": lambda u: "forms" in u and len(u.get("forms", [])) > 0,
        "forms": lambda u: "visitSchedules" in u,
        "scheduling": lambda u: any(k in u for k in ("dashboardCards", "reportCards")),
        "dashboard": lambda u: False,  # Manual advance to review
    }

    try:
        current_idx = phase_order.index(current_phase)
    except ValueError:
        return None

    trigger = phase_triggers.get(current_phase)
    if trigger and trigger(srs_update) and current_idx + 1 < len(phase_order):
        return phase_order[current_idx + 1]

    return None


# ---------------------------------------------------------------------------
# SRS mode activation/deactivation — uses the main /api/chat endpoint
# ---------------------------------------------------------------------------

class SRSModeRequest(BaseModel):
    session_id: str
    enabled: bool = True
    initial_srs: dict | None = None


@router.post("/srs/mode")
async def toggle_srs_mode(request: SRSModeRequest):
    """Activate or deactivate SRS building mode on a chat session.

    When active, the main /api/chat endpoint will:
    1. Augment the system prompt with SRS builder context + phase hints
    2. After streaming the response, extract structured SRS data
    3. Yield srs_update and phase SSE events alongside the normal text stream
    """
    from app.services.context_manager import (
        set_srs_state, get_srs_state, set_srs_phase, clear_srs_state,
    )

    if request.enabled:
        current = get_srs_state(request.session_id)
        if current is None:
            # Initialize SRS state
            initial = request.initial_srs or {}
            set_srs_state(request.session_id, initial)
            set_srs_phase(request.session_id, "start")
        return {
            "session_id": request.session_id,
            "srs_mode": True,
            "phase": "start",
        }
    else:
        # Deactivate
        clear_srs_state(request.session_id)
        return {"session_id": request.session_id, "srs_mode": False}


@router.get("/srs/state/{session_id}")
async def get_srs_state_endpoint(session_id: str):
    """Get the current SRS state for a session."""
    from app.services.context_manager import get_srs_state, get_srs_phase

    state = get_srs_state(session_id)
    if state is None:
        return {"session_id": session_id, "srs_mode": False}
    return {
        "session_id": session_id,
        "srs_mode": True,
        "phase": get_srs_phase(session_id),
        "srs_data": state,
    }
