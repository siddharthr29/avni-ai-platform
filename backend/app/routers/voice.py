import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import VoiceMapRequest, VoiceMapResponse
from app.services.voice_mapper import map_transcript

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/voice/map", response_model=VoiceMapResponse)
async def voice_map(request: VoiceMapRequest) -> VoiceMapResponse:
    """Map a voice transcript to form fields.

    Sends the transcript along with the form field definitions to Claude,
    which returns mapped field values with confidence scores.
    """
    if not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")

    if not request.form_json:
        raise HTTPException(status_code=400, detail="form_json is required")

    # Validate form_json has expected structure
    if "formElementGroups" not in request.form_json:
        raise HTTPException(
            status_code=422,
            detail="form_json must contain 'formElementGroups' array",
        )

    try:
        result = await map_transcript(
            transcript=request.transcript,
            form_json=request.form_json,
            language=request.language,
        )
        return VoiceMapResponse(
            fields=result["fields"],
            confidence=result["confidence"],
            unmapped_text=result["unmapped_text"],
        )
    except Exception as e:
        logger.exception("Voice mapping failed")
        raise HTTPException(
            status_code=500,
            detail=f"Voice mapping failed: {str(e)}",
        )
