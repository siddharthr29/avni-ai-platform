"""Audit, bundle versioning, and token usage endpoints.

Provides:
- Audit trail queries and summaries
- Bundle version listing, download, and comparison
- Token usage tracking and budget management
"""

import logging
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import db
from app.services.audit import get_audit_summary, get_audit_trail, get_user_activity
from app.services.bundle_versioning import (
    compare_versions,
    get_version,
    get_version_history,
    get_versions,
)
from app.services.token_budget import (
    check_budget,
    get_monthly_usage,
    get_top_users,
    get_usage_trend,
    set_budget,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Audit Trail ───────────────────────────────────────────────────────────────

@router.get("/audit/trail")
async def audit_trail(
    org_id: str = Query(..., description="Organisation ID"),
    action: str | None = Query(None, description="Filter by action type"),
    start_date: datetime | None = Query(None, description="Start date (ISO format)"),
    end_date: datetime | None = Query(None, description="End date (ISO format)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Get audit trail with optional filters."""
    entries = await get_audit_trail(
        org_id=org_id,
        limit=limit,
        offset=offset,
        action_filter=action,
        start_date=start_date,
        end_date=end_date,
    )
    # Serialise datetime values
    for entry in entries:
        for key, val in entry.items():
            if isinstance(val, datetime):
                entry[key] = val.isoformat()
    return {"entries": entries, "count": len(entries), "limit": limit, "offset": offset}


@router.get("/audit/user/{user_id}")
async def user_activity(
    user_id: str,
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Get recent activity for a specific user."""
    entries = await get_user_activity(user_id=user_id, limit=limit)
    for entry in entries:
        for key, val in entry.items():
            if isinstance(val, datetime):
                entry[key] = val.isoformat()
    return {"user_id": user_id, "entries": entries, "count": len(entries)}


@router.get("/audit/summary")
async def audit_summary(
    org_id: str = Query(..., description="Organisation ID"),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Get aggregate audit summary for the dashboard."""
    summary = await get_audit_summary(org_id=org_id, days=days)
    return summary


# ── Bundle Versions ───────────────────────────────────────────────────────────

@router.get("/bundles/versions")
async def list_bundle_versions(
    org_id: str = Query(..., description="Organisation ID"),
    limit: int = Query(20, ge=1, le=100),
) -> dict:
    """List bundle versions for an org."""
    versions = await get_versions(org_id=org_id, limit=limit)
    for v in versions:
        for key, val in v.items():
            if isinstance(val, datetime):
                v[key] = val.isoformat()
    return {"versions": versions, "count": len(versions)}


@router.get("/bundles/versions/compare")
async def compare_bundle_versions(
    v1: str = Query(..., description="First version ID"),
    v2: str = Query(..., description="Second version ID"),
) -> dict:
    """Compare two bundle versions and show what changed."""
    diff = await compare_versions(v1, v2)
    if "error" in diff:
        raise HTTPException(status_code=404, detail=diff["error"])
    return diff


@router.get("/bundles/versions/{version_id}")
async def get_bundle_version(version_id: str) -> dict:
    """Get a specific bundle version with full details."""
    version = await get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    for key, val in version.items():
        if isinstance(val, datetime):
            version[key] = val.isoformat()
    return version


@router.get("/bundles/versions/{version_id}/download")
async def download_bundle_version(version_id: str):
    """Download the bundle zip for a specific version."""
    version = await get_version(version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")

    file_path = version.get("file_path")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Bundle file not found on disk")

    filename = f"{version.get('bundle_name', 'bundle')}_v{version.get('version_number', 0)}.zip"
    return FileResponse(
        path=file_path,
        media_type="application/zip",
        filename=filename,
    )


# ── Token Usage ───────────────────────────────────────────────────────────────

@router.get("/usage/tokens")
async def token_usage(
    org_id: str = Query(..., description="Organisation ID"),
) -> dict:
    """Get current month's token usage for an org."""
    usage = await get_monthly_usage(org_id)
    return usage


@router.get("/usage/tokens/trend")
async def token_usage_trend(
    org_id: str = Query(..., description="Organisation ID"),
    months: int = Query(6, ge=1, le=24),
) -> dict:
    """Get token usage trend over the past N months."""
    trend = await get_usage_trend(org_id=org_id, months=months)
    return {"org_id": org_id, "months": months, "trend": trend}


@router.get("/usage/tokens/budget")
async def token_budget_status(
    org_id: str = Query(..., description="Organisation ID"),
) -> dict:
    """Get budget status for an org."""
    status = await check_budget(org_id)
    return status.to_dict()


class SetBudgetRequest(BaseModel):
    org_id: str
    monthly_limit_usd: float | None = None
    monthly_token_limit: int | None = None


@router.put("/usage/tokens/budget")
async def set_token_budget(request: SetBudgetRequest) -> dict:
    """Set monthly budget for an org (admin only)."""
    result = await set_budget(
        org_id=request.org_id,
        monthly_limit_usd=request.monthly_limit_usd,
        monthly_token_limit=request.monthly_token_limit,
    )
    if not result:
        raise HTTPException(status_code=500, detail="Failed to set budget")
    for key, val in result.items():
        if isinstance(val, datetime):
            result[key] = val.isoformat()
    return result
