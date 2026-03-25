"""Bundle regeneration API endpoint.

Accepts error input from multiple sources (server CSV, user feedback, validation
results) and applies fixes to generate a corrected bundle version.
"""

import json
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.bundle_generator import get_bundle_status, get_bundle_zip_path
from app.services.bundle_regenerator import (
    BundleRegenerator,
    ErrorSource,
    RegenerationResult,
    repackage_bundle_zip,
)

logger = logging.getLogger(__name__)

router = APIRouter()

regenerator = BundleRegenerator()


class RegenerateRequest(BaseModel):
    error_input: str = Field(
        description=(
            "Error content: CSV string from Avni server upload, "
            "JSON from validation API, or natural language from user."
        )
    )
    source: str = Field(
        description=(
            "Error source: 'server_upload', 'preflight', "
            "'validation_api', or 'user_feedback'."
        )
    )


class RegenerateResponse(BaseModel):
    success: bool
    changes_made: list[dict]
    remaining_errors: list[dict]
    needs_human_input: list[dict]
    iterations: int
    download_url: str | None = None
    bundle_id: str


@router.post(
    "/bundle/{bundle_id}/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_bundle(
    bundle_id: str,
    request: RegenerateRequest,
) -> RegenerateResponse:
    """Fix a bundle based on error feedback and produce a corrected version.

    Accepts error input as:
    - CSV string from a failed Avni server upload
    - JSON from the pre-flight or validation API
    - Natural language from a user chat message

    The system diagnoses errors, applies automatic fixes where possible,
    re-validates, and iterates up to 3 times. Returns the list of changes
    made, any remaining errors, and a download link for the fixed bundle.
    """
    # Validate source
    try:
        source = ErrorSource(request.source)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid source '{request.source}'. "
                f"Must be one of: {', '.join(s.value for s in ErrorSource)}"
            ),
        )

    # Locate the bundle directory
    bundle_dir = Path(settings.BUNDLE_OUTPUT_DIR) / bundle_id
    if not bundle_dir.is_dir():
        # Try to extract from zip if the directory doesn't exist
        zip_path = get_bundle_zip_path(bundle_id)
        if not zip_path:
            raise HTTPException(
                status_code=404,
                detail=f"Bundle '{bundle_id}' not found",
            )
        # Extract zip to bundle directory
        bundle_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(bundle_dir)
        # Handle nested directory (zip may contain a single folder)
        entries = [
            e for e in os.listdir(bundle_dir)
            if e != "__MACOSX"
        ]
        if len(entries) == 1 and (bundle_dir / entries[0]).is_dir():
            # Move contents up one level
            nested = bundle_dir / entries[0]
            for item in os.listdir(nested):
                src = nested / item
                dst = bundle_dir / item
                os.rename(str(src), str(dst))
            os.rmdir(str(nested))

    # Phase 1: Diagnose errors
    try:
        errors = await regenerator.diagnose(bundle_dir, request.error_input, source)
    except Exception as e:
        logger.exception("Error diagnosis failed for bundle %s", bundle_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to diagnose errors: {str(e)}",
        )

    if not errors:
        return RegenerateResponse(
            success=True,
            changes_made=[],
            remaining_errors=[],
            needs_human_input=[],
            iterations=0,
            download_url=f"/api/bundle/{bundle_id}/download",
            bundle_id=bundle_id,
        )

    logger.info(
        "Diagnosed %d errors for bundle %s (source=%s): %d auto-fixable",
        len(errors),
        bundle_id,
        source.value,
        sum(1 for e in errors if e.auto_fixable),
    )

    # Phase 2: Fix and validate in a loop
    try:
        result = await regenerator.fix_and_validate(bundle_dir, errors)
    except Exception as e:
        logger.exception("Fix-and-validate failed for bundle %s", bundle_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fix bundle: {str(e)}",
        )

    # Phase 3: Repackage the bundle zip
    download_url = None
    if result.changes_made:
        try:
            zip_path = repackage_bundle_zip(bundle_dir)
            download_url = f"/api/bundle/{bundle_id}/download"
            logger.info(
                "Regenerated bundle %s: %d changes, %d remaining errors",
                bundle_id,
                len(result.changes_made),
                len(result.remaining_errors),
            )
        except Exception as e:
            logger.warning("Failed to repackage bundle zip: %s", e)

    return RegenerateResponse(
        success=result.success,
        changes_made=result.changes_made,
        remaining_errors=[e.to_dict() for e in result.remaining_errors],
        needs_human_input=[e.to_dict() for e in result.needs_human_input],
        iterations=result.iterations,
        download_url=download_url,
        bundle_id=bundle_id,
    )
