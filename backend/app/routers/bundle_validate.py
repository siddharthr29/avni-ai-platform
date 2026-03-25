"""Bundle validation endpoint.

Uses the unified PreFlightValidator (6-layer validation) that mirrors
Avni server contracts exactly, replacing the older BundleValidator.
"""

import logging

from fastapi import APIRouter, HTTPException

from app.services.bundle_generator import get_bundle_zip_path
from app.services.preflight_validator import validate_bundle, fix_and_validate_bundle

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/bundle/{bundle_id}/validate")
async def validate_bundle_endpoint(bundle_id: str) -> dict:
    """Validate a generated bundle before uploading to Avni.

    Runs 6-layer pre-flight validation:
    1. Schema Validation — files, JSON, required fields, enums
    2. Reference Integrity — cross-file UUID references
    3. Collision Detection — duplicate names, UUIDs, display orders
    4. Business Rules — numeric ranges, form-type matching, invalid chars
    5. Rule Validation — JS syntax, declarative rules, concept refs
    6. Zip Structure — dependency order, extraneous files, sizes
    """
    zip_path = get_bundle_zip_path(bundle_id)
    if not zip_path:
        raise HTTPException(status_code=404, detail=f"Bundle {bundle_id} not found")

    result = validate_bundle(zip_path)
    result["bundle_id"] = bundle_id
    return result


@router.post("/bundle/{bundle_id}/validate-and-fix")
async def validate_and_fix_bundle_endpoint(bundle_id: str) -> dict:
    """Validate a bundle, apply auto-fixes, and re-validate.

    Auto-fixes include:
    - Concept name collision -> append UUID suffix
    - Missing UUID -> auto-generate
    - Duplicate display order -> renumber
    - Invalid characters -> sanitize
    - Missing cancellation form -> auto-generate
    """
    zip_path = get_bundle_zip_path(bundle_id)
    if not zip_path:
        raise HTTPException(status_code=404, detail=f"Bundle {bundle_id} not found")

    result = fix_and_validate_bundle(zip_path)
    result["bundle_id"] = bundle_id
    return result
