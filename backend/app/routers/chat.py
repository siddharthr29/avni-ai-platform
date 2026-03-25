"""Chat router — slim FastAPI endpoints delegating to service modules.

Endpoints:
- POST /api/chat — main chat with SSE streaming
- POST /api/org/context — set org context
- GET /api/org/context/{session_id} — get org context
- POST /api/chat/confirm — confirm/deny pending action
"""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import db
from app.middleware.content_filter import ContentFilterResult, filter_input, mask_pii
from app.models.schemas import ChatRequest
from app.services.action_detector import detect_action, execute_confirmed_action
from app.services.chat_handler import handle_chat_message
from app.services.context_manager import (
    _pending_actions,
    _sessions_fallback,
    get_org_context,
    set_org_context,
    get_history,
    save_message,
)
from app.services.intent_router import classify_intent

# Backward-compatible re-exports for tests and external consumers
_save_message = save_message
_get_history = get_history
_get_org_context = get_org_context
_set_org_context = set_org_context

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request/Response models ──────────────────────────────────────────────

class OrgContextRequest(BaseModel):
    session_id: str
    org_name: str | None = None
    sector: str | None = None
    org_context: str | None = None
    avni_auth_token: str | None = None


class OrgContextResponse(BaseModel):
    session_id: str
    org_context: dict[str, Any]


class ConfirmActionRequest(BaseModel):
    session_id: str
    action_id: str
    approved: bool
    message: str = ""


class ConfirmActionResponse(BaseModel):
    action_id: str
    status: str  # "approved" | "denied"


# ── Endpoints ────────────────────────────────────────────────────────────

@router.post("/org/context")
async def set_org_context_endpoint(request: OrgContextRequest) -> OrgContextResponse:
    """Set organisation context for a session (persists across messages)."""
    ctx = set_org_context(
        request.session_id,
        org_name=request.org_name,
        sector=request.sector,
        org_context=request.org_context,
        avni_auth_token=request.avni_auth_token,
    )
    return OrgContextResponse(session_id=request.session_id, org_context=ctx)


@router.get("/org/context/{session_id}")
async def get_org_context_endpoint(session_id: str) -> OrgContextResponse:
    """Get the current organisation context for a session."""
    ctx = get_org_context(session_id)
    return OrgContextResponse(session_id=session_id, org_context=ctx)


@router.post("/chat/confirm")
async def confirm_action(request: ConfirmActionRequest) -> ConfirmActionResponse:
    """Confirm or deny a pending action from the AI agent."""
    action = _pending_actions.pop(request.action_id, None)
    if not action:
        raise HTTPException(
            status_code=404,
            detail=f"Action {request.action_id} not found or already resolved",
        )

    if not request.approved:
        await save_message(
            request.session_id,
            "assistant",
            f"Action '{action.get('action_type', '')}' was denied by user.",
        )
        return ConfirmActionResponse(action_id=request.action_id, status="denied")

    result = await execute_confirmed_action(action)

    await save_message(
        request.session_id,
        "assistant",
        f"Action '{action.get('action_type', '')}' completed: {result}",
    )

    return ConfirmActionResponse(action_id=request.action_id, status="approved")


@router.post("/chat")
async def chat(request: ChatRequest, http_request: Request) -> EventSourceResponse:
    """Main chat endpoint with SSE streaming."""
    # Use authenticated user_id from JWT middleware
    authenticated_user_id = getattr(http_request.state, "user_id", None)
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    session_id = request.session_id
    message = request.message
    attachments = request.attachments

    # ── Input Guardrails ──
    filter_result: ContentFilterResult = filter_input(message)
    guardrail_warnings: list[str] = list(filter_result.warnings)

    effective_message = message
    if filter_result.pii_detected and filter_result.safe_text:
        effective_message = filter_result.safe_text
        await db.log_guardrail_event(
            event_type="pii_redacted",
            details={
                "pii_types": filter_result.pii_detected,
                "pii_counts": filter_result.pii_counts,
                "action": "fix",
                "message_preview": mask_pii(message[:200]),
            },
            session_id=session_id,
            user_id=authenticated_user_id,
        )

    if not filter_result.passed:
        await db.log_guardrail_event(
            event_type="injection_attempt" if filter_result.injection_detected else "content_filtered",
            details=filter_result.to_dict(),
            session_id=session_id,
            user_id=authenticated_user_id,
        )
        raise HTTPException(status_code=400, detail=filter_result.block_reason or "Message blocked by content filter")

    if filter_result.unsupported_language:
        await db.log_guardrail_event(
            event_type="unsupported_language",
            details={"message_preview": message[:100]},
            session_id=session_id,
            user_id=authenticated_user_id,
        )

    # Merge request org context with persisted org context
    persisted_ctx = get_org_context(session_id)
    org_name = request.org_name or persisted_ctx.get("org_name")
    sector = request.sector or persisted_ctx.get("sector")
    org_context_text = request.org_context or persisted_ctx.get("org_context")

    if request.org_name or request.sector or request.org_context:
        set_org_context(
            session_id,
            org_name=request.org_name,
            sector=request.sector,
            org_context=request.org_context,
        )

    # Resolve org_id for ban list scoping
    user_org_id = getattr(http_request.state, "org_id", "") or ""
    if not user_org_id and org_name:
        from app.db import _slugify_org
        user_org_id = _slugify_org(org_name)

    # Ban list check on input
    try:
        from app.services.ban_list import check_ban_list
        ban_result = await check_ban_list(effective_message, user_org_id)
        if ban_result["has_banned"]:
            banned_words = [b["word"] for b in ban_result["banned_words_found"]]
            reasons = [b["reason"] for b in ban_result["banned_words_found"] if b.get("reason")]
            reason_text = (" Reason: " + "; ".join(reasons)) if reasons else ""
            rephrase_msg = (
                f"Your message contains restricted terms: {', '.join(banned_words)}.{reason_text} "
                "Please rephrase your message without these terms."
            )
            await db.log_guardrail_event(
                event_type="ban_list_triggered",
                details={
                    "banned_words": banned_words,
                    "stage": "input",
                    "action": "rephrase",
                    "org_id": user_org_id,
                },
                session_id=session_id,
                user_id=authenticated_user_id,
            )
            raise HTTPException(status_code=400, detail=rephrase_msg)
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("Ban list input check skipped: %s", e)

    # Classify intent
    intent_result = await classify_intent(message, attachments)
    intent = intent_result.intent

    # Detect action requests
    action = detect_action(message)

    # Persist user message
    await save_message(session_id, "user", effective_message, user_id=authenticated_user_id)

    # Delegate to chat handler
    async def event_generator():
        async for event in handle_chat_message(
            message=message,
            effective_message=effective_message,
            session_id=session_id,
            authenticated_user_id=authenticated_user_id,
            attachments=attachments,
            org_name=org_name,
            sector=sector,
            org_context_text=org_context_text,
            user_org_id=user_org_id,
            action=action,
            intent=intent,
            intent_result=intent_result,
            guardrail_warnings=guardrail_warnings,
            filter_result=filter_result,
            byok_provider=request.byok_provider,
            byok_api_key=request.byok_api_key,
        ):
            yield event

    return EventSourceResponse(event_generator())
