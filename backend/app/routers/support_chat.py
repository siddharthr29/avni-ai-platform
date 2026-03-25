"""Support endpoints for non-technical NGO users.

Provides:
1. Guided troubleshooting flows (step-by-step decision trees)
2. FAQ search (no LLM needed — instant answers)
3. Quick diagnostics (check sync status, org health)
"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.troubleshoot import (
    get_flows,
    get_flow,
    get_step,
    search_flows,
)
from app.services.faq_service import (
    get_all_faqs,
    get_faqs_by_category,
    search_faqs,
    get_faq,
    mark_helpful,
    get_categories as get_faq_categories,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Troubleshooting Flows ────────────────────────────────────────────────────


@router.get("/support/troubleshoot")
async def list_troubleshoot_flows(q: str | None = Query(None, description="Search query")):
    """List all troubleshooting flows, optionally filtered by search query."""
    if q:
        results = search_flows(q)
        return {"flows": [_flow_summary(f) for f in results], "query": q}
    flows = get_flows()
    return {"flows": [_flow_summary(f) for f in flows]}


@router.get("/support/troubleshoot/{flow_id}")
async def get_troubleshoot_flow(flow_id: str):
    """Get a complete troubleshooting flow with all steps."""
    flow = get_flow(flow_id)
    if not flow:
        raise HTTPException(404, f"Troubleshooting flow '{flow_id}' not found")
    return {"flow": _flow_detail(flow)}


@router.get("/support/troubleshoot/{flow_id}/{step_id}")
async def get_troubleshoot_step(flow_id: str, step_id: str):
    """Get a specific step in a troubleshooting flow."""
    step = get_step(flow_id, step_id)
    if not step:
        raise HTTPException(404, f"Step '{step_id}' not found in flow '{flow_id}'")
    return {"step": step.to_dict()}


# ── FAQ ──────────────────────────────────────────────────────────────────────


@router.get("/support/faq")
async def list_faqs(category: str | None = Query(None, description="Filter by category")):
    """List all FAQs, optionally filtered by category."""
    if category:
        faqs = get_faqs_by_category(category)
    else:
        faqs = get_all_faqs()

    # Group by category
    grouped: dict[str, list[dict]] = {}
    for faq in faqs:
        d = faq.to_dict()
        grouped.setdefault(d["category"], []).append(d)

    return {"faqs": grouped, "total": len(faqs), "categories": get_faq_categories()}


@router.get("/support/faq/search")
async def search_faq(q: str = Query(..., min_length=2, description="Search query")):
    """Search FAQs by keyword."""
    results = search_faqs(q)
    return {"results": [f.to_dict() for f in results], "query": q, "total": len(results)}


@router.get("/support/faq/{faq_id}")
async def get_single_faq(faq_id: str):
    """Get a specific FAQ by ID."""
    faq = get_faq(faq_id)
    if not faq:
        raise HTTPException(404, f"FAQ '{faq_id}' not found")
    return {"faq": faq.to_dict()}


class FaqFeedbackRequest(BaseModel):
    helpful: bool = Field(description="Whether this FAQ was helpful")


@router.post("/support/faq/{faq_id}/helpful")
async def faq_feedback(faq_id: str, request: FaqFeedbackRequest):
    """Mark a FAQ as helpful or not helpful."""
    faq = get_faq(faq_id)
    if not faq:
        raise HTTPException(404, f"FAQ '{faq_id}' not found")
    mark_helpful(faq_id, request.helpful)
    return {"ok": True}


# ── Quick Diagnostics ────────────────────────────────────────────────────────


class QuickDiagnosisRequest(BaseModel):
    auth_token: str = Field(description="Avni AUTH-TOKEN")


@router.post("/support/quick-diagnosis")
async def quick_diagnosis(request: QuickDiagnosisRequest):
    """Run quick health checks against an Avni org.

    Checks:
    - Can connect to Avni server?
    - Is the org accessible?
    - Any recent errors?
    """
    import httpx
    from app.config import settings

    checks = {
        "server_reachable": False,
        "org_accessible": False,
        "org_name": None,
        "user_name": None,
        "recommendations": [],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Check server connectivity
            try:
                resp = await client.get(f"{settings.AVNI_BASE_URL}/api/ping")
                checks["server_reachable"] = resp.status_code < 500
            except Exception:
                checks["recommendations"].append(
                    "Cannot reach Avni server. Check your internet connection."
                )
                return {"diagnosis": checks}

            # Check org access with auth token
            try:
                headers = {"AUTH-TOKEN": request.auth_token}
                resp = await client.get(
                    f"{settings.AVNI_BASE_URL}/api/currentUser",
                    headers=headers,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    checks["org_accessible"] = True
                    checks["org_name"] = data.get("organisationName", "Unknown")
                    checks["user_name"] = data.get("name", "Unknown")
                elif resp.status_code == 401:
                    checks["recommendations"].append(
                        "Auth token is invalid or expired. Log out and log in again to get a new token."
                    )
                elif resp.status_code == 403:
                    checks["recommendations"].append(
                        "Your account does not have permission to access this org."
                    )
            except Exception as e:
                checks["recommendations"].append(f"Error checking org access: {e}")

            if not checks["recommendations"]:
                checks["recommendations"].append("Everything looks good! Your connection to Avni is healthy.")

    except Exception as e:
        checks["recommendations"].append(f"Diagnostic check failed: {e}")

    return {"diagnosis": checks}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _flow_summary(flow) -> dict:
    """Convert a flow to a summary dict (no step details)."""
    return {
        "id": flow.id,
        "title": flow.title,
        "description": flow.description,
        "category": flow.category,
        "step_count": len(flow.steps),
    }


def _flow_detail(flow) -> dict:
    """Convert a flow to a full detail dict."""
    return {
        "id": flow.id,
        "title": flow.title,
        "description": flow.description,
        "category": flow.category,
        "start_step": flow.start_step,
        "steps": {sid: s.to_dict() for sid, s in flow.steps.items()},
    }
