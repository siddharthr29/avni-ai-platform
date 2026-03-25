"""Org context management — session-scoped org context persistence.

Manages in-memory org contexts, bundle pending states, last bundle references,
pending actions, session fallback storage, and message history.
"""
import logging
import uuid
from typing import Any

from app import db

logger = logging.getLogger(__name__)

# In-memory fallback when DB is unavailable
_sessions_fallback: dict[str, list[dict]] = {}

# Org context store: session_id -> org context (persists across messages)
_org_contexts: dict[str, dict[str, Any]] = {}

# Bundle clarification state: session_id -> {"srs_text": str, "questions_asked": bool}
# Tracks sessions where we asked clarification questions before bundle generation
_bundle_pending: dict[str, dict[str, Any]] = {}

# Last generated bundle per session: session_id -> {"bundle_id": str, "srs_text": str}
# Used for corrections — "change X to Y" after a bundle was generated
_last_bundle: dict[str, dict[str, Any]] = {}

# In-memory pending actions store
_pending_actions: dict[str, dict] = {}  # action_id -> {session_id, action_type, details, ...}

MAX_HISTORY = 50

# SRS builder state per session
_srs_state: dict[str, dict[str, Any]] = {}
_srs_phases: dict[str, str] = {}


def get_srs_state(session_id: str) -> dict[str, Any] | None:
    """Get the SRS state being built for a session."""
    return _srs_state.get(session_id)


def set_srs_state(session_id: str, srs_data: dict[str, Any]) -> None:
    """Set/update the SRS state for a session."""
    _srs_state[session_id] = srs_data


def update_srs_state(session_id: str, update: dict[str, Any]) -> dict[str, Any]:
    """Merge an SRS update into the session's SRS state. Returns the merged state."""
    current = _srs_state.get(session_id, {})
    merged = _merge_srs(current, update)
    _srs_state[session_id] = merged
    return merged


def get_srs_phase(session_id: str) -> str:
    """Get the current SRS building phase for a session."""
    return _srs_phases.get(session_id, "start")


def set_srs_phase(session_id: str, phase: str) -> None:
    """Set the SRS building phase for a session."""
    _srs_phases[session_id] = phase


def clear_srs_state(session_id: str) -> None:
    """Remove SRS state for a session."""
    _srs_state.pop(session_id, None)
    _srs_phases.pop(session_id, None)


def _merge_srs(current: dict, update: dict) -> dict:
    """Merge an SRS update into current state with additive array merging."""
    merged = {**current}
    for key, val in update.items():
        if val is None:
            continue
        if key in ('forms', 'programs', 'subjectTypes'):
            # Merge by name
            existing = list(merged.get(key, []))
            for item in val:
                name = item.get('name', '') if isinstance(item, dict) else str(item)
                idx = next((i for i, e in enumerate(existing)
                           if (e.get('name', '') if isinstance(e, dict) else str(e)).lower() == name.lower()), -1)
                if idx >= 0:
                    existing[idx] = {**(existing[idx] if isinstance(existing[idx], dict) else {}), **(item if isinstance(item, dict) else {})}
                else:
                    existing.append(item)
            merged[key] = existing
        elif key in ('encounterTypes', 'generalEncounterTypes', 'groups'):
            # String arrays: union
            seen = {s.lower() for s in merged.get(key, [])}
            combined = list(merged.get(key, []))
            for s in val:
                if isinstance(s, str) and s.lower() not in seen:
                    combined.append(s)
                    seen.add(s.lower())
            merged[key] = combined
        elif key in ('visitSchedules', 'programEncounterMappings', 'eligibilityRules'):
            # Merge by key field
            key_field = 'schedule_encounter' if key == 'visitSchedules' else 'program'
            existing = list(merged.get(key, []))
            for item in val:
                kf = item.get(key_field, '')
                idx = next((i for i, e in enumerate(existing) if e.get(key_field, '').lower() == kf.lower()), -1)
                if idx >= 0:
                    existing[idx] = {**existing[idx], **item}
                else:
                    existing.append(item)
            merged[key] = existing
        elif isinstance(val, dict):
            merged[key] = {**merged.get(key, {}), **val}
        else:
            merged[key] = val
    return merged


def get_org_context(session_id: str) -> dict[str, Any]:
    """Get the persisted org context for a session."""
    return _org_contexts.get(session_id, {})


def set_org_context(session_id: str, **kwargs) -> dict[str, Any]:
    """Set/update org context for a session. Only updates non-None values."""
    if session_id not in _org_contexts:
        _org_contexts[session_id] = {}
    for key, value in kwargs.items():
        if value is not None:
            _org_contexts[session_id][key] = value
    return _org_contexts[session_id]


async def get_history(session_id: str, limit: int = 20) -> list[dict]:
    """Load chat history from DB, falling back to in-memory."""
    if db.is_connected():
        rows = await db.get_recent_messages(session_id, limit=limit)
        return [{"role": r["role"], "content": r["content"]} for r in rows]
    # In-memory fallback
    msgs = _sessions_fallback.get(session_id, [])
    return msgs[-limit:]


async def ensure_session(session_id: str, user_id: str = "anonymous") -> None:
    """Ensure the session row exists in DB (idempotent). Handles race conditions."""
    if not db.is_connected() or not db._pool:
        return
    async with db._pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM sessions WHERE id = $1", session_id)
        if not exists:
            try:
                await conn.execute(
                    """
                    INSERT INTO sessions (id, user_id, title)
                    VALUES ($1, $2, 'New Chat')
                    ON CONFLICT (id) DO NOTHING
                    """,
                    session_id, user_id,
                )
            except Exception as e:
                logger.debug("Auto-create session failed (race ok): %s", e)


async def save_message(session_id: str, role: str, content: str, user_id: str = "anonymous") -> None:
    """Save a message to DB, falling back to in-memory."""
    if db.is_connected():
        await ensure_session(session_id, user_id=user_id)
        try:
            await db.add_message(
                message_id=str(uuid.uuid4()),
                session_id=session_id,
                role=role,
                content=content,
            )
        except Exception as e:
            logger.warning("Failed to save message: %s", e)
    else:
        if session_id not in _sessions_fallback:
            _sessions_fallback[session_id] = []
        _sessions_fallback[session_id].append({"role": role, "content": content})
        if len(_sessions_fallback[session_id]) > MAX_HISTORY:
            _sessions_fallback[session_id] = _sessions_fallback[session_id][-MAX_HISTORY:]
