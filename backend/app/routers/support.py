import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import SupportDiagnoseRequest, SupportDiagnoseResponse
from app.services.support_diagnosis import diagnose

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/support/diagnose",
    response_model=SupportDiagnoseResponse,
)
async def diagnose_issue(
    request: SupportDiagnoseRequest,
) -> SupportDiagnoseResponse:
    """Diagnose a common Avni issue from a natural-language description.

    Matches the description against known issue patterns (sync, form
    visibility, rule errors, upload errors, data quality, permissions,
    performance). When the match is ambiguous, Claude is used for
    additional classification and analysis.
    """
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="description cannot be empty")

    try:
        result = await diagnose(
            description=request.description,
            error_message=request.error_message,
            context=request.context,
        )
        return SupportDiagnoseResponse(
            pattern=result["pattern"],
            diagnosis=result["diagnosis"],
            checks=result["checks"],
            common_fixes=result["common_fixes"],
            confidence=result["confidence"],
            ai_analysis=result.get("ai_analysis"),
        )
    except Exception as exc:
        logger.exception("Support diagnosis failed")
        raise HTTPException(
            status_code=500,
            detail=f"Diagnosis failed: {exc}",
        )
