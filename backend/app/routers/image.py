import json
import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.schemas import ImageExtractResponse
from app.services.image_extractor import extract_from_image

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_IMAGE_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "image/bmp", "image/tiff",
}

MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/image/extract", response_model=ImageExtractResponse)
async def image_extract(
    image: UploadFile = File(..., description="Image file to extract data from"),
    form_json: str = Form(..., description="Avni form JSON definition as a string"),
) -> ImageExtractResponse:
    """Extract structured form data from an image.

    Accepts a multipart form upload with an image file and the form JSON
    definition. Uses Claude Vision to read the image and map visible data
    to form fields.
    """
    # Validate content type
    content_type = image.content_type or "image/jpeg"
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported image type: {content_type}. "
                   f"Allowed types: {', '.join(sorted(ALLOWED_IMAGE_TYPES))}",
        )

    # Read image bytes
    image_bytes = await image.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Image file is empty")
    if len(image_bytes) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Image file too large. Maximum size: {MAX_IMAGE_SIZE // (1024 * 1024)} MB",
        )

    # Parse form_json
    try:
        form_data = json.loads(form_json)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid form_json: {str(e)}",
        )

    if "formElementGroups" not in form_data:
        raise HTTPException(
            status_code=422,
            detail="form_json must contain 'formElementGroups' array",
        )

    try:
        result = await extract_from_image(
            image_bytes=image_bytes,
            form_json=form_data,
            image_type=content_type,
        )
        return ImageExtractResponse(
            fields=result["fields"],
            confidence=result["confidence"],
            notes=result["notes"],
        )
    except Exception as e:
        logger.exception("Image extraction failed")
        raise HTTPException(
            status_code=500,
            detail=f"Image extraction failed: {str(e)}",
        )
