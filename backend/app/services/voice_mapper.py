import json
import logging
from typing import Any

from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)


def _build_field_context(form_json: dict[str, Any]) -> str:
    """Extract field descriptions from a form JSON to provide context to Claude.

    Builds a structured description of each field including its name, data type,
    allowed options (for coded), valid range (for numeric), and whether it is mandatory.
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


VOICE_MAP_SYSTEM_PROMPT = """You are an expert at mapping voice transcript data to structured form fields.

Given a voice transcript and a list of form fields with their types and constraints, extract the values mentioned in the transcript and map them to the correct fields.

Rules:
1. Only map values that are clearly mentioned or can be confidently inferred from the transcript.
2. For Coded fields, map to the exact option name from the allowed options list. If the spoken value is a synonym or abbreviation, match it to the closest valid option.
3. For Numeric fields, extract the numeric value only. Convert spoken numbers (e.g., "one hundred twenty") to digits (120). Respect the unit and valid range.
4. For Date fields, output in YYYY-MM-DD format. Interpret relative dates (e.g., "yesterday", "last Monday") relative to today.
5. For multi-select Coded fields, return a list of selected options.
6. Assign a confidence score (0.0 to 1.0) to each mapped field based on how clearly it was stated.
7. Include any transcript text that could not be mapped to any field in the "unmapped_text" field.

Respond with ONLY a JSON object in this exact format:
{
  "fields": {"Field Name": value, ...},
  "confidence": {"Field Name": 0.95, ...},
  "unmapped_text": "remaining text that was not mapped"
}

Do not include any other text outside the JSON object."""


async def map_transcript(
    transcript: str,
    form_json: dict[str, Any],
    language: str = "en",
) -> dict[str, Any]:
    """Map a voice transcript to form fields using Claude.

    Args:
        transcript: The voice transcript text.
        form_json: The Avni form JSON definition.
        language: Language code of the transcript (e.g., 'en', 'hi', 'mr').

    Returns:
        A dict with 'fields', 'confidence', and 'unmapped_text'.
    """
    field_context = _build_field_context(form_json)
    form_name = form_json.get("name", "Unknown Form")

    language_names = {
        "en": "English", "hi": "Hindi", "mr": "Marathi", "gu": "Gujarati",
        "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "bn": "Bengali",
        "or": "Odia", "pa": "Punjabi", "ml": "Malayalam",
    }
    language_name = language_names.get(language, language)

    user_message = (
        f"Form: {form_name}\n"
        f"Transcript language: {language_name}\n\n"
        f"Transcript:\n\"{transcript}\"\n\n"
        f"Form fields:\n{field_context}\n\n"
        f"Map the transcript values to these form fields."
    )

    try:
        response_text = await claude_client.complete(
            messages=[{"role": "user", "content": user_message}],
            system_prompt=VOICE_MAP_SYSTEM_PROMPT,
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
                "unmapped_text": result.get("unmapped_text", ""),
            }
        except json.JSONDecodeError:
            logger.error("Failed to parse Claude response for voice mapping: %s", response_text[:500])
            return {
                "fields": {},
                "confidence": {},
                "unmapped_text": transcript,
            }
    except Exception as e:
        logger.error("LLM call failed during voice mapping: %s", str(e))
        return {
            "fields": {},
            "confidence": {},
            "unmapped_text": transcript,
        }
