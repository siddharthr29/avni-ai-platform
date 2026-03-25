"""FastAPI router for the pre-built SRS template library.

Exposes endpoints to list, retrieve, customise, and directly generate
Avni bundles from domain-specific SRS templates.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from typing import Any

from app.models.schemas import BundleStatus, BundleStatusType, SRSData
from app.services.bundle_generator import generate_from_srs
from app.services.template_library import (
    customize_template,
    get_template,
    get_template_categories,
    list_templates,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class TemplateCustomizeRequest(BaseModel):
    """Body for POST /api/templates/{domain}/customize."""
    orgName: str | None = Field(default=None, description="Override organisation name")
    groups: list[str] | None = Field(default=None, description="Replace user groups")
    addressLevelTypes: list[dict[str, Any]] | None = Field(default=None, description="Replace address hierarchy")
    subjectTypes: list[dict[str, Any]] | None = Field(default=None, description="Replace subject types")
    addPrograms: list[dict[str, Any]] | None = Field(default=None, description="Programs to add")
    removePrograms: list[str] | None = Field(default=None, description="Program names to remove")
    addEncounterTypes: list[str] | None = Field(default=None, description="Encounter types to add")
    removeEncounterTypes: list[str] | None = Field(default=None, description="Encounter type names to remove")
    addForms: list[dict[str, Any]] | None = Field(default=None, description="Form definitions to add")
    removeForms: list[str] | None = Field(default=None, description="Form names to remove")
    programEncounterMappings: list[dict[str, Any]] | None = Field(default=None, description="Override program-encounter mappings")
    generalEncounterTypes: list[str] | None = Field(default=None, description="Override general encounter types")


class TemplateSummary(BaseModel):
    domain: str
    name: str
    description: str
    icon: str
    subjectTypes: list[str]
    programs: list[str]
    formsCount: int
    totalFields: int
    encounterTypes: list[str]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[TemplateSummary])
async def list_all_templates() -> list[dict[str, Any]]:
    """Return summary metadata for every available template."""
    return list_templates()


@router.get("/templates/categories", response_model=list[str])
async def template_categories() -> list[str]:
    """Return the list of available template domain keys."""
    return get_template_categories()


@router.get("/templates/{domain}")
async def get_domain_template(domain: str) -> dict[str, Any]:
    """Return the full SRS template for the given domain.

    The response is a complete SRSData-compatible dict that can be passed
    to ``POST /api/bundle/generate`` as ``srs_data``.
    """
    try:
        return get_template(domain)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/templates/{domain}/customize")
async def customize_domain_template(
    domain: str,
    request: TemplateCustomizeRequest,
) -> dict[str, Any]:
    """Apply overrides to a template and return the customised SRS.

    Useful for tweaking a template before generating a bundle. The caller
    can then pass the result to ``POST /api/bundle/generate``.
    """
    overrides = request.model_dump(exclude_none=True)
    try:
        return customize_template(domain, overrides)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/templates/{domain}/generate", response_model=BundleStatus)
async def generate_from_template(
    domain: str,
    background_tasks: BackgroundTasks,
    request: TemplateCustomizeRequest | None = None,
) -> BundleStatus:
    """Generate a full Avni bundle directly from a template.

    Optionally accepts customisation overrides in the request body.
    Returns a ``BundleStatus`` with a bundle ID that can be polled via
    ``GET /api/bundle/{bundle_id}/status`` and downloaded via
    ``GET /api/bundle/{bundle_id}/download``.
    """
    try:
        if request is not None:
            overrides = request.model_dump(exclude_none=True)
            if overrides:
                tpl = customize_template(domain, overrides)
            else:
                tpl = get_template(domain)
        else:
            tpl = get_template(domain)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    # Convert the template dict into an SRSData model
    try:
        srs_data = SRSData(**tpl)
    except Exception as exc:
        logger.exception("Failed to parse template '%s' as SRSData", domain)
        raise HTTPException(
            status_code=500,
            detail=f"Template produced invalid SRS data: {exc}",
        )

    if not srs_data.forms:
        raise HTTPException(
            status_code=422,
            detail="Template has no form definitions — cannot generate bundle",
        )

    bundle_id = str(uuid.uuid4())

    status = BundleStatus(
        id=bundle_id,
        status=BundleStatusType.PENDING,
        progress=0,
        message=f"Bundle generation from '{domain}' template queued",
    )

    async def _run(srs: SRSData, bid: str) -> None:
        try:
            await generate_from_srs(srs, bid)
        except Exception:
            logger.exception("Background bundle generation failed: %s", bid)

    background_tasks.add_task(_run, srs_data, bundle_id)

    return status
