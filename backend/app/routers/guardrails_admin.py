"""Guardrails admin endpoints — manage ban lists, view events, get stats.

Provides admin APIs for:
- Ban list management (per-org banned words)
- Guardrail event log (audit trail with filters)
- Guardrail trigger statistics
- Current guardrail configuration
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.config import settings
from app.middleware.permissions import get_current_user
from app.services.ban_list import (
    add_banned_word,
    get_ban_list,
    remove_banned_word,
    seed_default_ban_lists,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guardrails", tags=["Guardrails Admin"])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_admin(request: Request) -> tuple[str, str, str]:
    """Return (user_id, role, org_id) or raise 403."""
    user = get_current_user(request)
    role = user.role.value
    if role not in ("platform_admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Forbidden: admin role required")
    org_id: str = getattr(request.state, "org_id", "") or ""
    return user.user_id, role, org_id


# ── Request/Response Models ─────────────────────────────────────────────────

class BanWordRequest(BaseModel):
    word: str = Field(..., min_length=1, max_length=100)
    reason: str = Field("", max_length=500)
    org_id: str = Field("", description="Org ID to scope the ban word. Empty = global.")


class BanWordResponse(BaseModel):
    word: str
    reason: str
    org_id: str
    status: str


class GuardrailConfigResponse(BaseModel):
    guardrails_enabled: bool
    pii_detection_enabled: bool
    injection_detection_enabled: bool
    gender_bias_check_enabled: bool
    ban_list_enabled: bool
    guardrail_on_fail_default: str
    low_confidence_threshold: float


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/config")
async def get_guardrail_config(request: Request) -> GuardrailConfigResponse:
    """Get the current guardrail configuration."""
    _require_admin(request)
    return GuardrailConfigResponse(
        guardrails_enabled=settings.GUARDRAILS_ENABLED,
        pii_detection_enabled=settings.PII_DETECTION_ENABLED,
        injection_detection_enabled=settings.INJECTION_DETECTION_ENABLED,
        gender_bias_check_enabled=settings.GENDER_BIAS_CHECK_ENABLED,
        ban_list_enabled=settings.BAN_LIST_ENABLED,
        guardrail_on_fail_default=settings.GUARDRAIL_ON_FAIL_DEFAULT,
        low_confidence_threshold=settings.LOW_CONFIDENCE_THRESHOLD,
    )


@router.post("/ban-list")
async def add_ban_word_endpoint(request: Request, body: BanWordRequest) -> BanWordResponse:
    """Add a word to an org's ban list. If org_id is empty, adds to global list."""
    user_id, role, user_org_id = _require_admin(request)

    # Determine target org
    target_org = body.org_id or user_org_id or "__global__"

    # Org admins can only manage their own org's ban list
    if role == "org_admin" and target_org != user_org_id and target_org != "__global__":
        raise HTTPException(status_code=403, detail="Org admins can only manage their own org's ban list")

    await add_banned_word(
        org_id=target_org,
        word=body.word,
        reason=body.reason,
        created_by=user_id,
    )

    await db.log_admin_action(
        actor_id=user_id,
        action="ban_word_added",
        target_type="ban_list",
        target_id=target_org,
        details={"word": body.word, "reason": body.reason},
    )

    return BanWordResponse(
        word=body.word.lower().strip(),
        reason=body.reason,
        org_id=target_org,
        status="added",
    )


@router.delete("/ban-list/{word}")
async def remove_ban_word_endpoint(
    request: Request,
    word: str,
    org_id: str = "",
) -> BanWordResponse:
    """Remove a word from an org's ban list."""
    user_id, role, user_org_id = _require_admin(request)

    target_org = org_id or user_org_id or "__global__"

    if role == "org_admin" and target_org != user_org_id and target_org != "__global__":
        raise HTTPException(status_code=403, detail="Org admins can only manage their own org's ban list")

    await remove_banned_word(org_id=target_org, word=word)

    await db.log_admin_action(
        actor_id=user_id,
        action="ban_word_removed",
        target_type="ban_list",
        target_id=target_org,
        details={"word": word},
    )

    return BanWordResponse(
        word=word.lower().strip(),
        reason="",
        org_id=target_org,
        status="removed",
    )


@router.get("/ban-list")
async def list_ban_words(
    request: Request,
    org_id: str = "",
) -> list[dict[str, Any]]:
    """List an org's banned words. If org_id is empty, uses the caller's org."""
    user_id, role, user_org_id = _require_admin(request)

    target_org = org_id or user_org_id or "__global__"

    if role == "org_admin" and target_org != user_org_id and target_org != "__global__":
        raise HTTPException(status_code=403, detail="Org admins can only view their own org's ban list")

    items = await get_ban_list(target_org)

    # Also include global ban list items if viewing org-specific
    if target_org != "__global__":
        global_items = await get_ban_list("__global__")
        for item in global_items:
            item["scope"] = "global"
        for item in items:
            item["scope"] = "org"
        items = global_items + items

    return items


@router.get("/events")
async def get_guardrail_events(
    request: Request,
    user_id: str | None = None,
    session_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Get guardrail event log with optional filters."""
    _require_admin(request)
    events = await db.get_guardrail_events(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        limit=min(limit, 500),
    )
    return events


@router.get("/stats")
async def get_guardrail_stats(request: Request) -> dict[str, Any]:
    """Get aggregate guardrail trigger statistics."""
    _require_admin(request)
    stats = await db.get_guardrail_stats()
    return stats


@router.post("/ban-list/seed-defaults")
async def seed_defaults_endpoint(request: Request) -> dict[str, str]:
    """Seed default ban lists for Indian NGO contexts.

    Only adds words if the global ban list is empty (first-time setup).
    Platform admin only.
    """
    user_id, role, _ = _require_admin(request)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Only platform admins can seed defaults")

    await seed_default_ban_lists()

    await db.log_admin_action(
        actor_id=user_id,
        action="ban_list_defaults_seeded",
        target_type="ban_list",
        target_id="__global__",
    )

    return {"status": "ok", "message": "Default ban lists seeded (if global list was empty)"}
