import json
import logging
from typing import Any

from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)


def _build_field_context(form_json: dict[str, Any]) -> str:
    """Extract field descriptions from a form JSON to provide context to Claude.

    Same structure as voice_mapper to keep the mapping interface consistent.
    """
    lines: list[str] = []
    groups = form_json.get("formElementGroups", [])

    for group in groups:
        group_name = group.get("name", "Unnamed Group")
        elements = group.get("formElements", [])
        if not elements:
            continue

        lines.append(f"\n## {group_name}")

        for elem in elements:
            concept = elem.get("concept", {})
            field_name = elem.get("name") or concept.get("name", "Unknown")
            data_type = concept.get("dataType", "Text")
            mandatory = elem.get("mandatory", False)
            elem_type = elem.get("type", "SingleSelect")

            desc = f"- **{field_name}** (type: {data_type}"

            if mandatory:
                desc += ", MANDATORY"

            if data_type == "Coded":
                answers = concept.get("answers", [])
                options = [a.get("name", "") for a in answers if a.get("name")]
                if options:
                    desc += f", options: [{', '.join(options)}]"
                if elem_type == "MultiSelect":
                    desc += ", multi-select"
                else:
                    desc += ", single-select"

            elif data_type == "Numeric":
                unit = concept.get("unit")
                if unit:
                    desc += f", unit: {unit}"
                low = concept.get("lowAbsolute")
                high = concept.get("highAbsolute")
                if low is not None or high is not None:
                    range_str = f"{low if low is not None else '...'} to {high if high is not None else '...'}"
                    desc += f", valid range: {range_str}"

            elif data_type == "Date":
                desc += ", format: YYYY-MM-DD"

            elif data_type == "Time":
                desc += ", format: HH:MM"

            desc += ")"
            lines.append(desc)

    return "\n".join(lines)


IMAGE_EXTRACT_SYSTEM_PROMPT = """You are an expert at extracting structured data from images of paper forms, registers, health cards, and other documents used in field data collection.

Given an image and a list of form fields with their types and constraints, extract the values visible in the image and map them to the correct fields.

Rules:
1. Carefully read all text, numbers, checkmarks, and written entries in the image.
2. For Coded fields, map to the exact option name from the allowed options list. If the handwritten value is a close match, use the closest valid option.
3. For Numeric fields, extract the numeric value. Respect the unit and valid range constraints.
4. For Date fields, output in YYYY-MM-DD format.
5. For multi-select Coded fields, return a list of all checked/marked options.
6. Assign a confidence score (0.0 to 1.0) to each extracted field based on legibility and certainty.
7. If parts of the image are unclear or illegible, note this in the "notes" field.
8. Only extract values that you can see in the image. Do not guess or fabricate values.

Respond with ONLY a JSON object in this exact format:
{
  "fields": {"Field Name": value, ...},
  "confidence": {"Field Name": 0.95, ...},
  "notes": "any observations about image quality, illegible areas, etc."
}

Do not include any other text outside the JSON object."""


async def extract_from_image(
    image_bytes: bytes,
    form_json: dict[str, Any],
    image_type: str = "image/jpeg",
) -> dict[str, Any]:
    """Extract structured form data from an image using Claude Vision.

    Args:
        image_bytes: Raw bytes of the image.
        form_json: The Avni form JSON definition.
        image_type: MIME type of the image (e.g., 'image/jpeg', 'image/png').

    Returns:
        A dict with 'fields', 'confidence', and 'notes'.
    """
    field_context = _build_field_context(form_json)
    form_name = form_json.get("name", "Unknown Form")

    user_message = (
        f"Form: {form_name}\n\n"
        f"Form fields:\n{field_context}\n\n"
        f"Extract the values from this image and map them to the form fields above."
    )

    response_text = await claude_client.complete_with_vision(
        messages=[{"role": "user", "content": user_message}],
        system_prompt=IMAGE_EXTRACT_SYSTEM_PROMPT,
        image_data=image_bytes,
        image_media_type=image_type,
    )

    # Parse the JSON response
    try:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

        result = json.loads(cleaned)
        return {
            "fields": result.get("fields", {}),
            "confidence": result.get("confidence", {}),
            "notes": result.get("notes", ""),
        }
    except json.JSONDecodeError:
        logger.error(
            "Failed to parse Claude response for image extraction: %s",
            response_text[:500],
        )
        return {
            "fields": {},
            "confidence": {},
            "notes": "Failed to parse extraction results from the image.",
        }
