"""Avni Organisation management endpoints.

Connects the AI platform to Avni server for:
1. Bundle upload (apply AI-generated bundles to real Avni orgs)
2. Bundle diff/preview (see what changes before applying)
3. Upload status tracking
4. Template org application
"""

import logging
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.avni_org_service import AvniOrgError, avni_org_service
from app.services.bundle_generator import get_bundle_zip_path, get_bundle_status
from app.services.feedback import feedback_service

logger = logging.getLogger(__name__)

router = APIRouter()


class BundleUploadRequest(BaseModel):
    bundle_id: str = Field(description="ID of a generated bundle to upload")
    auth_token: str = Field(description="Avni AUTH-TOKEN for the target org")
    auto_approve: bool = Field(default=True, description="Auto-approve metadata changes")


class BundleCompareRequest(BaseModel):
    bundle_id: str = Field(description="ID of a generated bundle to compare")
    auth_token: str = Field(description="Avni AUTH-TOKEN for the target org")


class TrialOrgRequest(BaseModel):
    bundle_id: str = Field(description="ID of a generated bundle to provision with")
    org_name: str = Field(description="Name for the new trial organisation")
    admin_auth_token: str = Field(description="SuperAdmin AUTH-TOKEN for org creation")
    admin_user_name: str = Field(default="Admin", description="Display name for the org admin user")


class OrgCreateRequest(BaseModel):
    org_name: str = Field(description="Name for the new organisation")
    admin_auth_token: str = Field(description="SuperAdmin AUTH-TOKEN")
    db_user: str | None = Field(default=None, description="Database username (auto-generated if None)")


class UserCreateRequest(BaseModel):
    username: str = Field(description="Login username (e.g. user@orgname)")
    name: str = Field(description="Display name")
    auth_token: str = Field(description="Avni AUTH-TOKEN for org admin")


class TemplateApplyRequest(BaseModel):
    template_id: int = Field(description="Template organisation ID to apply")
    auth_token: str = Field(description="Avni AUTH-TOKEN")


@router.get("/avni/org/current")
async def get_current_org(auth_token: str) -> dict:
    """Get the current Avni organisation for the authenticated user."""
    try:
        org = await avni_org_service.get_current_org(auth_token)
        return {"org": org}
    except AvniOrgError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/avni/bundle/upload")
async def upload_bundle_to_avni(request: BundleUploadRequest) -> dict:
    """Upload an AI-generated bundle to an Avni organisation.

    Flow:
    1. AI generates bundle via /api/bundle/generate
    2. User reviews via /api/bundle/review/{id} (optional edits)
    3. User uploads via this endpoint with their Avni auth token
    4. Avni server processes the zip via BundleZipFileImporter

    The user must have UploadMetadataAndData privilege in the target org.
    """
    # Find the generated bundle zip
    zip_path = get_bundle_zip_path(request.bundle_id)
    if not zip_path or not os.path.isfile(zip_path):
        raise HTTPException(
            status_code=404,
            detail=f"Bundle {request.bundle_id} not found or not yet generated. "
                   "Use /api/bundle/generate first, then /api/bundle/{id}/status to check completion.",
        )

    try:
        result = await avni_org_service.upload_bundle(
            auth_token=request.auth_token,
            bundle_zip_path=zip_path,
            auto_approve=request.auto_approve,
        )
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avni/bundle/upload-validated")
async def upload_bundle_validated(request: BundleUploadRequest) -> dict:
    """Validate then upload a bundle using two-pass strategy.

    1. Runs bundle validation (duplicate concepts, UUID mismatches, etc.)
    2. If validation passes, uploads concepts first, then full bundle
    """
    zip_path = get_bundle_zip_path(request.bundle_id)
    if not zip_path or not os.path.isfile(zip_path):
        raise HTTPException(
            status_code=404,
            detail=f"Bundle {request.bundle_id} not found or not yet generated. "
                   "Use /api/bundle/generate first, then /api/bundle/{id}/status to check completion.",
        )

    # Validate first (unified 6-layer pre-flight validation)
    from app.services.preflight_validator import validate_bundle
    validation = validate_bundle(zip_path)
    if not validation["valid"]:
        return {
            "status": "validation_failed",
            "bundle_id": request.bundle_id,
            "validation": validation,
            "message": f"Bundle has {validation['error_count']} errors. Fix before uploading.",
        }

    # Two-pass upload
    try:
        result = await avni_org_service.upload_bundle_two_pass(
            auth_token=request.auth_token,
            bundle_zip_path=zip_path,
            auto_approve=request.auto_approve,
        )
        result["validation"] = validation
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avni/bundle/compare")
async def compare_bundle_with_org(request: BundleCompareRequest) -> dict:
    """Compare an AI-generated bundle against the current org metadata.

    Shows what would be added, changed, or removed if the bundle
    were uploaded. Uses Avni's MetadataDiffService.

    This is the "preview before apply" step.
    """
    zip_path = get_bundle_zip_path(request.bundle_id)
    if not zip_path or not os.path.isfile(zip_path):
        raise HTTPException(status_code=404, detail="Bundle not found")

    try:
        diff = await avni_org_service.compare_bundle(
            auth_token=request.auth_token,
            bundle_zip_path=zip_path,
        )
        return {"bundle_id": request.bundle_id, "diff": diff}
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/avni/bundle/upload/status")
async def bundle_upload_status(auth_token: str) -> dict:
    """Check the status of recent bundle upload jobs in Avni."""
    try:
        jobs = await avni_org_service.get_upload_status(auth_token)
        return {"jobs": jobs}
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/avni/templates")
async def list_templates(auth_token: str) -> dict:
    """List available template organisations that can be cloned."""
    try:
        templates = await avni_org_service.get_template_organisations(auth_token)
        return {"templates": templates}
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avni/templates/apply")
async def apply_template(request: TemplateApplyRequest) -> dict:
    """Apply a template organisation to the current org.

    Copies all metadata (concepts, forms, programs, rules, etc.)
    from the template org. Cannot be applied to Production/UAT orgs.
    """
    try:
        result = await avni_org_service.apply_template(
            auth_token=request.auth_token,
            template_id=request.template_id,
        )
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Trial Org Provisioning ──────────────────────────────────────────────────


@router.post("/avni/org/create")
async def create_organisation(request: OrgCreateRequest) -> dict:
    """Create a new Avni organisation (SuperAdmin only).

    Creates the DB user, schema, and org record on avni-server.
    """
    try:
        result = await avni_org_service.create_organisation(
            admin_auth_token=request.admin_auth_token,
            org_name=request.org_name,
            db_user=request.db_user,
        )
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avni/user/create")
async def create_user(request: UserCreateRequest) -> dict:
    """Create a user in the current Avni organisation.

    Requires EditUserConfiguration privilege.
    """
    try:
        result = await avni_org_service.create_user(
            auth_token=request.auth_token,
            username=request.username,
            name=request.name,
        )
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avni/trial/provision")
async def provision_trial_org(request: TrialOrgRequest) -> dict:
    """One-click trial org provisioning.

    End-to-end flow for "users without Avni domain knowledge":
    1. Creates a new organisation on Avni server
    2. Uploads the AI-generated bundle (two-pass)
    3. Creates an admin user
    4. Returns credentials and next steps

    Requires SuperAdmin AUTH-TOKEN. The generated bundle must exist
    (use /api/bundle/generate first).
    """
    zip_path = get_bundle_zip_path(request.bundle_id)
    if not zip_path or not os.path.isfile(zip_path):
        raise HTTPException(
            status_code=404,
            detail=f"Bundle {request.bundle_id} not found. Generate it first.",
        )

    try:
        result = await avni_org_service.provision_trial_org(
            admin_auth_token=request.admin_auth_token,
            org_name=request.org_name,
            bundle_zip_path=zip_path,
            admin_user_name=request.admin_user_name,
        )
        return result
    except AvniOrgError as e:
        raise HTTPException(status_code=400, detail=str(e))
