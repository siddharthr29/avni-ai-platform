"""Avni Organisation and Bundle Upload Service.

Integrates with Avni server APIs to:
1. Upload metadata bundles (zip files) to existing organisations
2. Check upload job status
3. Compare bundles before applying (metadata diff)

Based on avni-server's actual API:
- POST /import/new (type=metadataZip) — Upload bundle zip
- GET /import/status — Check batch job status
- POST /web/metadataDiff — Compare bundle against current org metadata
- GET /organisation/current — Get current org info

Auth: All endpoints require AUTH-TOKEN header (Cognito/Keycloak JWT)
Permissions: UploadMetadataAndData privilege required for bundle upload
"""

import io
import json
import logging
import os
import zipfile
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0


class AvniOrgService:
    """Service for organisation management and bundle operations against Avni server."""

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.AVNI_BASE_URL).rstrip("/")

    def _headers(self, auth_token: str) -> dict[str, str]:
        return {
            "AUTH-TOKEN": auth_token,
        }

    async def get_current_org(self, auth_token: str) -> dict:
        """Get the current organisation for the authenticated user."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self.base_url}/organisation/current",
                headers=self._headers(auth_token),
            )
        if resp.status_code == 401:
            raise AvniOrgError("Invalid or expired AUTH-TOKEN")
        resp.raise_for_status()
        return resp.json()

    async def upload_bundle(
        self,
        auth_token: str,
        bundle_zip_path: str,
        auto_approve: bool = True,
    ) -> dict:
        """Upload a metadata bundle zip to the current Avni organisation.

        This triggers Avni's batch import job (BundleZipFileImporter).
        The bundle is processed in the order of files in the zip.

        Args:
            auth_token: Avni AUTH-TOKEN for the target org admin
            bundle_zip_path: Path to the .zip file on disk
            auto_approve: Whether to auto-approve changes (default True)

        Returns:
            {"status": "submitted", "message": "..."} on success
        """
        if not os.path.isfile(bundle_zip_path):
            raise AvniOrgError(f"Bundle zip not found: {bundle_zip_path}")

        headers = self._headers(auth_token)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            with open(bundle_zip_path, "rb") as f:
                resp = await client.post(
                    f"{self.base_url}/import/new",
                    headers=headers,
                    data={
                        "type": "metadataZip",
                        "autoApprove": str(auto_approve).lower(),
                        "locationUploadMode": "relaxed",
                        "locationHierarchy": "",
                        "encounterUploadMode": "relaxed",
                    },
                    files={"file": ("bundle.zip", f, "application/zip")},
                )

        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN or insufficient permissions")
        if resp.status_code == 403:
            raise AvniOrgError(
                "Insufficient permissions. User needs UploadMetadataAndData privilege."
            )
        if resp.status_code >= 400:
            raise AvniOrgError(f"Upload failed (HTTP {resp.status_code}): {resp.text[:300]}")

        return {"status": "submitted", "message": "Bundle upload job started"}

    async def upload_bundle_from_bytes(
        self,
        auth_token: str,
        zip_bytes: bytes,
        auto_approve: bool = True,
    ) -> dict:
        """Upload a bundle zip from in-memory bytes."""
        headers = self._headers(auth_token)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/import/new",
                headers=headers,
                data={
                    "type": "metadataZip",
                    "autoApprove": str(auto_approve).lower(),
                    "locationUploadMode": "relaxed",
                    "locationHierarchy": "",
                    "encounterUploadMode": "relaxed",
                },
                files={"file": ("bundle.zip", zip_bytes, "application/zip")},
            )

        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN or insufficient permissions")
        if resp.status_code == 403:
            raise AvniOrgError(
                "Insufficient permissions. User needs UploadMetadataAndData privilege."
            )
        if resp.status_code >= 400:
            raise AvniOrgError(f"Upload failed (HTTP {resp.status_code}): {resp.text[:300]}")

        return {"status": "submitted", "message": "Bundle upload job started"}

    async def get_upload_status(self, auth_token: str) -> list[dict]:
        """Get the status of recent upload jobs."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self.base_url}/import/status",
                headers=self._headers(auth_token),
                params={"size": 5, "sort": "createTime,desc"},
            )
        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN")
        resp.raise_for_status()
        data = resp.json()
        # Avni returns a paginated response
        if isinstance(data, dict) and "content" in data:
            return data["content"]
        return data if isinstance(data, list) else []

    async def compare_bundle(
        self,
        auth_token: str,
        bundle_zip_path: str,
    ) -> dict:
        """Compare a bundle against the current org metadata.

        Uses Avni's MetadataDiffService to show what would change
        if this bundle were uploaded. Useful for preview before apply.
        """
        headers = self._headers(auth_token)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            with open(bundle_zip_path, "rb") as f:
                resp = await client.post(
                    f"{self.base_url}/web/metadataDiff",
                    headers=headers,
                    files={"file": ("bundle.zip", f, "application/zip")},
                )

        if resp.status_code >= 400:
            raise AvniOrgError(f"Diff failed (HTTP {resp.status_code}): {resp.text[:300]}")
        return resp.json()

    async def get_template_organisations(self, auth_token: str) -> list[dict]:
        """Get available template organisations for cloning."""
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                f"{self.base_url}/web/templateOrganisations",
                headers=self._headers(auth_token),
            )
        if resp.status_code >= 400:
            return []
        return resp.json() if isinstance(resp.json(), list) else []

    async def apply_template(
        self,
        auth_token: str,
        template_id: int,
    ) -> dict:
        """Apply a template organisation to the current org.

        This copies all metadata (concepts, forms, programs, etc.) from
        the template org. Requires UploadMetadataAndData + DeleteOrganisationConfiguration
        + EditOrganisationConfiguration privileges.
        """
        headers = self._headers(auth_token)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/web/templateOrganisations/{template_id}/apply",
                headers=headers,
            )

        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN")
        if resp.status_code == 403:
            raise AvniOrgError("Insufficient permissions for template application")
        if resp.status_code >= 400:
            raise AvniOrgError(f"Template apply failed: {resp.text[:300]}")

        job_uuid = resp.text.strip().strip('"')
        return {"status": "submitted", "job_uuid": job_uuid}


    async def upload_bundle_two_pass(
        self,
        auth_token: str,
        bundle_zip_path: str,
        auto_approve: bool = True,
    ) -> dict:
        """Two-pass upload: concepts first, then full bundle.

        Required for fresh orgs where concepts must exist before forms reference them.
        """
        import asyncio

        # Step 1: Extract concepts.json from the bundle
        concepts_data = None
        with zipfile.ZipFile(bundle_zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith("concepts.json") and "__MACOSX" not in name:
                    concepts_data = zf.read(name)
                    break

        if not concepts_data:
            # No concepts.json found, do single upload
            return await self.upload_bundle(auth_token, bundle_zip_path, auto_approve)

        # Step 2: Create a zip with only concepts.json
        concepts_zip = io.BytesIO()
        with zipfile.ZipFile(concepts_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("concepts.json", concepts_data)
        concepts_zip.seek(0)

        # Step 3: Upload concepts-only zip
        logger.info("Two-pass upload: uploading concepts.json first")
        result1 = await self.upload_bundle_from_bytes(
            auth_token=auth_token,
            zip_bytes=concepts_zip.read(),
            auto_approve=auto_approve,
        )

        # Step 4: Brief wait for concepts to be processed
        await asyncio.sleep(3)

        # Step 5: Upload full bundle
        logger.info("Two-pass upload: uploading full bundle")
        result2 = await self.upload_bundle(
            auth_token=auth_token,
            bundle_zip_path=bundle_zip_path,
            auto_approve=auto_approve,
        )

        return {
            "status": "submitted",
            "message": "Two-pass upload completed (concepts first, then full bundle)",
            "pass1": result1,
            "pass2": result2,
        }


    # ─── Trial Org Provisioning ──────────────────────────────────────────

    async def create_organisation(
        self,
        admin_auth_token: str,
        org_name: str,
        db_user: str | None = None,
        user_type: str = "Organisation",
    ) -> dict:
        """Create a new organisation on Avni server.

        Requires SuperAdmin role. Creates DB user + schema.

        Args:
            admin_auth_token: SuperAdmin AUTH-TOKEN
            org_name: Name of the organisation
            db_user: DB username (auto-generated from org_name if None)
            user_type: "Organisation" (default) or "Trial"
        """
        if not db_user:
            db_user = org_name.lower().replace(" ", "_").replace("-", "_")[:30]

        payload = {
            "name": org_name,
            "dbUser": db_user,
            "usernameSuffix": f"@{db_user}",
            "account": {"name": org_name},
            "category": {"name": user_type},
        }

        headers = self._headers(admin_auth_token)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/organisation",
                headers=headers,
                json=payload,
            )

        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN or not a SuperAdmin")
        if resp.status_code == 403:
            raise AvniOrgError("SuperAdmin role required for org creation")
        if resp.status_code >= 400:
            raise AvniOrgError(
                f"Org creation failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        return resp.json() if resp.text.strip() else {"name": org_name, "dbUser": db_user}

    async def create_user(
        self,
        auth_token: str,
        username: str,
        name: str,
        org_uuid: str | None = None,
        catch_all: bool = True,
    ) -> dict:
        """Create a user in the current Avni organisation.

        Requires EditUserConfiguration privilege.

        Args:
            auth_token: AUTH-TOKEN for org admin
            username: Login username (e.g. user@orgname)
            name: Display name
            org_uuid: Organisation UUID (uses current org if None)
            catch_all: Assign to all catchments
        """
        payload: dict[str, Any] = {
            "username": username,
            "name": name,
            "orgAdmin": False,
            "admin": False,
            "catchmentId": None,
            "settings": {"locale": "en"},
        }
        if org_uuid:
            payload["organisationUUID"] = org_uuid

        headers = self._headers(auth_token)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(
                f"{self.base_url}/user",
                headers=headers,
                json=payload,
            )

        if resp.status_code == 401:
            raise AvniOrgError("Invalid AUTH-TOKEN")
        if resp.status_code == 403:
            raise AvniOrgError("EditUserConfiguration privilege required")
        if resp.status_code >= 400:
            raise AvniOrgError(
                f"User creation failed (HTTP {resp.status_code}): {resp.text[:300]}"
            )

        return resp.json() if resp.text.strip() else {"username": username, "name": name}

    async def provision_trial_org(
        self,
        admin_auth_token: str,
        org_name: str,
        bundle_zip_path: str,
        admin_user_name: str = "Admin",
    ) -> dict:
        """End-to-end trial org provisioning.

        1. Create organisation (SuperAdmin)
        2. Upload bundle (two-pass)
        3. Return org details + credentials

        This is the "users without Avni knowledge" flow from the concept note:
        upload requirements → get an Avni app to try out.
        """
        import asyncio

        # Step 1: Create org
        logger.info("Provisioning trial org: %s", org_name)
        org = await self.create_organisation(
            admin_auth_token=admin_auth_token,
            org_name=org_name,
            user_type="Trial",
        )
        org_db_user = org.get("dbUser", org_name.lower().replace(" ", "_"))

        # Step 2: Wait for org schema to be created
        await asyncio.sleep(2)

        # Step 3: Upload bundle using two-pass strategy
        logger.info("Uploading bundle to new org: %s", org_name)
        upload_result = await self.upload_bundle_two_pass(
            auth_token=admin_auth_token,
            bundle_zip_path=bundle_zip_path,
            auto_approve=True,
        )

        # Step 4: Create admin user for the trial org
        admin_username = f"admin@{org_db_user}"
        try:
            user = await self.create_user(
                auth_token=admin_auth_token,
                username=admin_username,
                name=admin_user_name,
            )
        except AvniOrgError:
            user = {"username": admin_username, "note": "User creation may require separate step"}

        return {
            "status": "provisioned",
            "organisation": org,
            "upload": upload_result,
            "user": user,
            "credentials": {
                "username": admin_username,
                "note": "Password set via Keycloak/Cognito admin console",
            },
            "next_steps": [
                f"Set password for {admin_username} in Keycloak",
                "Download Avni field app from Play Store",
                f"Login with {admin_username}",
            ],
        }


class AvniOrgError(Exception):
    """Raised for Avni organisation API errors."""


avni_org_service = AvniOrgService()
