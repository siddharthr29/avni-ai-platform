"""Feedback, bundle review, and Avni org integration endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import db
from app.routers.bundle import verify_bundle_lock_ownership
from app.services.feedback import feedback_service

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Feedback Models ──────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    session_id: str
    message_id: str
    rating: str = Field(description="'up', 'down', or 'correction'")
    correction: str | None = Field(
        default=None,
        description="User's corrected version of the AI response",
    )
    metadata: dict[str, Any] | None = None


class BundleEditRequest(BaseModel):
    bundle_id: str
    file_name: str = Field(description="File to edit: concepts.json, forms/MyForm.json, etc.")
    content: Any = Field(description="New content for the file (JSON object)")
    user_id: str | None = Field(
        default=None,
        description="User ID for lock ownership verification",
    )


class BundleApproveRequest(BaseModel):
    bundle_id: str


# ── Feedback Endpoints ───────────────────────────────────────────────────────

@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest) -> dict:
    """Submit feedback on an AI response.

    - rating="up": Positive signal, response was helpful
    - rating="down": Negative signal, optionally with correction text
    - rating="correction": User provides the correct answer

    Corrections are indexed into the RAG knowledge base so the AI
    learns from mistakes and doesn't repeat them.
    """
    if request.rating not in ("up", "down", "correction"):
        raise HTTPException(status_code=400, detail="rating must be 'up', 'down', or 'correction'")

    result = await feedback_service.save_feedback(
        session_id=request.session_id,
        message_id=request.message_id,
        rating=request.rating,
        correction=request.correction,
        metadata=request.metadata,
    )
    return result


@router.get("/feedback/stats")
async def feedback_stats() -> dict:
    """Get aggregate feedback statistics."""
    return await db.get_feedback_stats()


@router.get("/feedback/corrections")
async def recent_corrections(limit: int = 50) -> dict:
    """Get recent user corrections for review and training data extraction."""
    corrections = await db.get_corrections(limit=limit)
    return {"corrections": corrections, "count": len(corrections)}


# ── Bundle Review Endpoints ──────────────────────────────────────────────────

@router.get("/bundle/review")
async def list_pending_bundles() -> dict:
    """List all bundles pending review."""
    return {"bundles": feedback_service.list_pending_bundles()}


@router.get("/bundle/review/{bundle_id}")
async def get_bundle_for_review(bundle_id: str) -> dict:
    """Get a generated bundle for review before applying to Avni.

    Returns all generated files so the user can inspect and edit them.
    """
    bundle = feedback_service.get_pending_bundle(bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found or already applied")
    return {
        "bundle_id": bundle_id,
        "status": bundle["status"],
        "files": bundle["files"],
        "edit_count": len(bundle["edits"]),
        "edits": bundle["edits"],
    }


@router.post("/bundle/review/edit")
async def edit_bundle_file(request: BundleEditRequest) -> dict:
    """Edit a specific file in a pending bundle before applying.

    Allows users to fix concepts, forms, rules, etc. before the
    bundle is uploaded to Avni. All edits are tracked.

    If the bundle is locked by another user, the request is rejected with 409.
    Pass user_id in the body to identify yourself as the lock owner.
    """
    if request.user_id:
        await verify_bundle_lock_ownership(request.bundle_id, request.user_id)

    result = feedback_service.edit_bundle_file(
        bundle_id=request.bundle_id,
        file_name=request.file_name,
        content=request.content,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/bundle/review/approve")
async def approve_bundle(request: BundleApproveRequest) -> dict:
    """Approve a reviewed bundle, making it ready for upload to Avni."""
    bundle = feedback_service.approve_bundle(request.bundle_id)
    if not bundle:
        raise HTTPException(status_code=404, detail="Bundle not found")
    return {"bundle_id": request.bundle_id, "status": "approved"}
