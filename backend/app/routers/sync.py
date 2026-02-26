import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import SaveObservationsRequest, SaveObservationsResponse
from app.services.avni_sync import AvniAuthError, AvniApiError, avni_sync_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/avni/save-observations",
    response_model=SaveObservationsResponse,
)
async def save_observations(
    request: SaveObservationsRequest,
) -> SaveObservationsResponse:
    """Save mapped voice/image data to Avni.

    Creates a subject if *subject_uuid* is not provided, then creates an
    encounter (general or program) with the given observation fields.
    """
    if not request.fields:
        raise HTTPException(status_code=400, detail="fields cannot be empty")
    if not request.encounter_type.strip():
        raise HTTPException(status_code=400, detail="encounter_type is required")
    if not request.auth_token.strip():
        raise HTTPException(status_code=400, detail="auth_token is required")

    try:
        result = await avni_sync_service.save_observations(request.model_dump())
        return SaveObservationsResponse(
            success=result["success"],
            subject_uuid=result["subject_uuid"],
            encounter_uuid=result.get("encounter_uuid"),
            message=result["message"],
        )
    except AvniAuthError as exc:
        logger.warning("Avni auth error: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))
    except AvniApiError as exc:
        logger.error("Avni API error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error saving observations")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save observations: {exc}",
        )


@router.get("/avni/form/{form_uuid}")
async def get_form_definition(
    form_uuid: str,
    auth_token: str = Query(..., description="Avni AUTH-TOKEN"),
) -> dict:
    """Fetch a form definition from Avni by UUID.

    Useful for obtaining form structure before voice/image mapping.
    """
    if not auth_token.strip():
        raise HTTPException(status_code=400, detail="auth_token is required")

    try:
        return await avni_sync_service.get_form_definition(form_uuid, auth_token)
    except AvniAuthError as exc:
        logger.warning("Avni auth error: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))
    except AvniApiError as exc:
        logger.error("Avni API error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error fetching form definition")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch form definition: {exc}",
        )


@router.get("/avni/subjects/search")
async def search_subjects(
    q: str = Query(..., description="Subject name to search for"),
    auth_token: str = Query(..., description="Avni AUTH-TOKEN"),
) -> list[dict]:
    """Search for subjects by name in Avni."""
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query (q) cannot be empty")
    if not auth_token.strip():
        raise HTTPException(status_code=400, detail="auth_token is required")

    try:
        return await avni_sync_service.search_subjects(q, auth_token)
    except AvniAuthError as exc:
        logger.warning("Avni auth error: %s", exc)
        raise HTTPException(status_code=401, detail=str(exc))
    except AvniApiError as exc:
        logger.error("Avni API error: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error searching subjects")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to search subjects: {exc}",
        )
