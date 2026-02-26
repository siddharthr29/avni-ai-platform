import logging
import uuid
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Timeout for Avni API calls (seconds)
_AVNI_TIMEOUT = 30.0


class AvniSyncService:
    """Service for saving data to Avni via its REST API.

    Uses httpx.AsyncClient to communicate with the Avni server. Every public
    method requires an *auth_token* so that calls are made on behalf of the
    correct Avni user.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.AVNI_BASE_URL).rstrip("/")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self, auth_token: str) -> dict[str, str]:
        return {
            "AUTH-TOKEN": auth_token,
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        auth_token: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        """Issue an HTTP request to the Avni API and return the JSON response."""
        url = f"{self.base_url}{path}"
        headers = self._headers(auth_token)

        async with httpx.AsyncClient(timeout=_AVNI_TIMEOUT) as client:
            response = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )

        if response.status_code == 401:
            raise AvniAuthError("Invalid or expired AUTH-TOKEN")
        if response.status_code == 403:
            raise AvniAuthError("Insufficient permissions for this operation")
        if response.status_code >= 400:
            detail = response.text[:500] if response.text else str(response.status_code)
            raise AvniApiError(
                f"Avni API error (HTTP {response.status_code}): {detail}"
            )

        # Some Avni endpoints return 200/201 with empty body
        if not response.text or not response.text.strip():
            return {}
        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create_subject(self, subject_data: dict, auth_token: str) -> dict:
        """Create a new subject (individual / household / group) in Avni.

        *subject_data* should follow the Avni subject creation payload format.
        A UUID is generated automatically if not provided.

        Returns the payload as echoed back by Avni (or the sent payload with
        the generated UUID when Avni returns an empty body).
        """
        if "uuid" not in subject_data or not subject_data["uuid"]:
            subject_data["uuid"] = str(uuid.uuid4())

        if "registrationDate" not in subject_data:
            from datetime import date

            subject_data["registrationDate"] = date.today().isoformat()

        logger.info(
            "Creating Avni subject type=%s uuid=%s",
            subject_data.get("subjectType", "Individual"),
            subject_data["uuid"],
        )

        result = await self._request(
            "POST", "/api/subjects", auth_token, json_body=subject_data
        )

        # Avni may return an empty body on success; ensure we always hand
        # back at least the uuid.
        if not result:
            result = {"uuid": subject_data["uuid"]}
        return result

    async def update_subject(
        self, subject_uuid: str, subject_data: dict, auth_token: str
    ) -> dict:
        """Update an existing subject."""
        subject_data["uuid"] = subject_uuid
        logger.info("Updating Avni subject uuid=%s", subject_uuid)

        result = await self._request(
            "PUT",
            f"/api/subjects/{subject_uuid}",
            auth_token,
            json_body=subject_data,
        )
        if not result:
            result = {"uuid": subject_uuid}
        return result

    async def create_encounter(self, encounter_data: dict, auth_token: str) -> dict:
        """Create a general encounter in Avni.

        *encounter_data* must include at minimum: encounterType,
        encounterDateTime, subjectUUID, and observations.
        """
        if "uuid" not in encounter_data or not encounter_data["uuid"]:
            encounter_data["uuid"] = str(uuid.uuid4())

        logger.info(
            "Creating Avni encounter type=%s uuid=%s subject=%s",
            encounter_data.get("encounterType"),
            encounter_data["uuid"],
            encounter_data.get("subjectUUID"),
        )

        result = await self._request(
            "POST", "/api/encounters", auth_token, json_body=encounter_data
        )
        if not result:
            result = {"uuid": encounter_data["uuid"]}
        return result

    async def create_program_enrolment(
        self, enrolment_data: dict, auth_token: str
    ) -> dict:
        """Enroll a subject into a program."""
        if "uuid" not in enrolment_data or not enrolment_data["uuid"]:
            enrolment_data["uuid"] = str(uuid.uuid4())

        logger.info(
            "Creating Avni program enrolment program=%s uuid=%s subject=%s",
            enrolment_data.get("program"),
            enrolment_data["uuid"],
            enrolment_data.get("subjectUUID"),
        )

        result = await self._request(
            "POST", "/api/programEnrolments", auth_token, json_body=enrolment_data
        )
        if not result:
            result = {"uuid": enrolment_data["uuid"]}
        return result

    async def create_program_encounter(
        self, encounter_data: dict, auth_token: str
    ) -> dict:
        """Create a program encounter in Avni.

        *encounter_data* must include at minimum: encounterType,
        encounterDateTime, programEnrolmentUUID, and observations.
        """
        if "uuid" not in encounter_data or not encounter_data["uuid"]:
            encounter_data["uuid"] = str(uuid.uuid4())

        logger.info(
            "Creating Avni program encounter type=%s uuid=%s enrolment=%s",
            encounter_data.get("encounterType"),
            encounter_data["uuid"],
            encounter_data.get("programEnrolmentUUID"),
        )

        result = await self._request(
            "POST", "/api/programEncounters", auth_token, json_body=encounter_data
        )
        if not result:
            result = {"uuid": encounter_data["uuid"]}
        return result

    async def get_form_definition(self, form_uuid: str, auth_token: str) -> dict:
        """Fetch a form definition from Avni by its UUID."""
        logger.info("Fetching Avni form definition uuid=%s", form_uuid)
        return await self._request(
            "GET",
            f"/api/forms/export",
            auth_token,
            params={"formUUID": form_uuid},
        )

    async def search_subjects(self, query: str, auth_token: str) -> list[dict]:
        """Search for subjects by name.

        Returns a list of matching subject summaries.
        """
        logger.info("Searching Avni subjects query=%r", query)
        result = await self._request(
            "GET",
            "/api/subjects/search",
            auth_token,
            params={"name": query},
        )
        # The Avni search endpoint returns a paginated wrapper with a
        # ``content`` list.
        if isinstance(result, dict) and "content" in result:
            return result["content"]
        if isinstance(result, list):
            return result
        return []

    async def save_observations(self, data: dict) -> dict:
        """High-level helper: save voice/image mapped fields to Avni.

        Orchestrates subject creation (if needed) and encounter creation
        from a single request payload.

        Parameters inside *data*:
            subject_uuid  - str | None  (create new subject if absent)
            encounter_type - str
            program       - str | None  (if set, creates a program encounter)
            fields        - dict        (mapped observation values)
            auth_token    - str
            subject_type  - str         (default "Individual")
            first_name    - str | None
            last_name     - str | None

        Returns:
            {"success": bool, "subject_uuid": str,
             "encounter_uuid": str | None, "message": str}
        """
        auth_token: str = data["auth_token"]
        subject_uuid: str | None = data.get("subject_uuid")
        encounter_type: str = data["encounter_type"]
        program: str | None = data.get("program")
        fields: dict = data.get("fields", {})
        subject_type: str = data.get("subject_type", "Individual")
        first_name: str | None = data.get("first_name")
        last_name: str | None = data.get("last_name")

        # 1. Create the subject if no UUID was supplied
        if not subject_uuid:
            subject_payload: dict[str, Any] = {
                "subjectType": subject_type,
                "observations": {},
            }
            if first_name:
                subject_payload["firstName"] = first_name
            if last_name:
                subject_payload["lastName"] = last_name

            subject_result = await self.create_subject(subject_payload, auth_token)
            subject_uuid = subject_result.get("uuid", subject_payload.get("uuid", ""))

        # 2. Build the encounter
        from datetime import datetime, timezone

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        encounter_uuid: str | None = None

        if program:
            # For a program encounter we first need an enrolment.
            # In a real workflow the enrolment UUID would already exist;
            # here we create one if the caller didn't provide it.
            enrolment_uuid = data.get("enrolment_uuid")
            if not enrolment_uuid:
                enrolment_result = await self.create_program_enrolment(
                    {
                        "subjectUUID": subject_uuid,
                        "program": program,
                        "enrolmentDateTime": now_iso,
                        "observations": {},
                    },
                    auth_token,
                )
                enrolment_uuid = enrolment_result.get("uuid", "")

            enc_result = await self.create_program_encounter(
                {
                    "encounterType": encounter_type,
                    "encounterDateTime": now_iso,
                    "programEnrolmentUUID": enrolment_uuid,
                    "observations": fields,
                },
                auth_token,
            )
            encounter_uuid = enc_result.get("uuid")
        else:
            enc_result = await self.create_encounter(
                {
                    "encounterType": encounter_type,
                    "encounterDateTime": now_iso,
                    "subjectUUID": subject_uuid,
                    "observations": fields,
                },
                auth_token,
            )
            encounter_uuid = enc_result.get("uuid")

        return {
            "success": True,
            "subject_uuid": subject_uuid,
            "encounter_uuid": encounter_uuid,
            "message": "Observations saved to Avni successfully",
        }


# ------------------------------------------------------------------
# Custom exceptions
# ------------------------------------------------------------------


class AvniAuthError(Exception):
    """Raised when Avni returns 401 or 403."""


class AvniApiError(Exception):
    """Raised for non-auth Avni HTTP errors."""


# Module-level singleton
avni_sync_service = AvniSyncService()
