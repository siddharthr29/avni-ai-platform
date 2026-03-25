import logging
from typing import Any

from app.services.claude_client import claude_client

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Known issue patterns distilled from 90K+ Avni support tickets
# ------------------------------------------------------------------

ISSUE_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": "sync",
        "keywords": [
            "sync",
            "not syncing",
            "sync failed",
            "data not showing",
            "offline",
            "sync error",
            "sync stuck",
            "sync incomplete",
        ],
        "diagnosis": "Sync issues are the most common Avni problem.",
        "checks": [
            "Check if the device has internet connectivity",
            "Check if the user's AUTH-TOKEN is valid (Settings > Auth token status)",
            "Check if the server is reachable (try opening the Avni URL in browser)",
            "Check sync telemetry: SELECT * FROM sync_telemetry WHERE user_id = X ORDER BY sync_start_time DESC LIMIT 5",
            "Check for large payloads: SELECT entity_name, count FROM sync_telemetry_detail WHERE sync_telemetry_id = X ORDER BY count DESC",
            "If sync is partially working, check entity_sync_status table for which entities are failing",
        ],
        "common_fixes": [
            "Reset sync: Settings > Reset sync (caution: this re-downloads all data)",
            "Force logout and re-login",
            "Check server logs for 500 errors during sync",
            "Increase sync timeout if dataset is large",
        ],
    },
    {
        "pattern": "form_not_showing",
        "keywords": [
            "form not showing",
            "form missing",
            "can't see form",
            "encounter not available",
            "no encounter button",
            "form not appearing",
            "form not visible",
            "form not loading",
        ],
        "diagnosis": "Form not appearing usually means missing or incorrect formMappings.",
        "checks": [
            "Check formMappings.json has entry for this form + subjectType + encounterType",
            "Check operationalEncounterTypes.json includes this encounterType",
            "Check user group has privilege to view/register this form type",
            "Check eligibility rules if form has encounter eligibility check",
        ],
        "common_fixes": [
            "Add correct formMapping with subjectTypeUUID + encounterTypeUUID + programUUID",
            "Add user group privilege for this encounter type",
            "Check and fix eligibility rule if it's blocking the form",
        ],
    },
    {
        "pattern": "rule_error",
        "keywords": [
            "rule error",
            "rule not working",
            "skip logic broken",
            "calculation wrong",
            "visit not scheduling",
            "rule failure",
            "javascript error",
            "decision rule",
        ],
        "diagnosis": "Rule errors are usually caused by incorrect concept UUIDs or syntax errors.",
        "checks": [
            "Verify all concept UUIDs in the rule match concepts.json",
            "Check JavaScript syntax (missing brackets, semicolons)",
            "Verify the rule type matches where it's attached (ViewFilter on form element, VisitSchedule on form)",
            "Check rule execution logs on the server",
            "Test the rule with sample data",
        ],
        "common_fixes": [
            "Fix concept UUID references",
            "Use FormElementStatusBuilder correctly (pass programEncounter, not encounter)",
            "For visit scheduling, ensure encounterType name matches exactly",
            "Add null checks for optional observations",
        ],
    },
    {
        "pattern": "upload_error",
        "keywords": [
            "upload failed",
            "bundle error",
            "import error",
            "zip error",
            "concept error",
            "upload error",
            "metadata upload",
            "bulk upload",
        ],
        "diagnosis": "Bundle upload errors are usually caused by ordering, duplicate UUIDs, or missing references.",
        "checks": [
            "Check zip file ordering (addressLevelTypes must come before subjectTypes, etc.)",
            "Check for duplicate concept names or UUIDs",
            "Check all referenced UUIDs exist (form elements -> concepts, formMappings -> forms)",
            "Verify JSON syntax in all files",
        ],
        "common_fixes": [
            "Regenerate the bundle with correct ordering",
            "Remove duplicate concepts",
            "Fix UUID references",
            "Use the bundle validator before uploading",
        ],
    },
    {
        "pattern": "data_quality",
        "keywords": [
            "wrong data",
            "data mismatch",
            "duplicate data",
            "missing data",
            "data correction",
            "data issue",
            "incorrect data",
            "data not matching",
        ],
        "diagnosis": "Data quality issues need careful diagnosis.",
        "checks": [
            "Check if the issue is in sync or in actual data entry",
            "Check voided/non-voided status of the entities",
            "Check audit logs for who modified the data and when",
            "For duplicates, check if same subject was registered twice (different UUIDs, same name/DOB)",
        ],
        "common_fixes": [
            "Void duplicate entries (don't delete)",
            "Use data fix scripts for bulk corrections",
            "Set up validation rules to prevent future data quality issues",
            "Add mandatory fields for key data points",
        ],
    },
    {
        "pattern": "permissions",
        "keywords": [
            "permission",
            "access denied",
            "can't register",
            "can't edit",
            "can't void",
            "privilege",
            "forbidden",
            "not authorized",
            "no access",
        ],
        "diagnosis": "Permission issues are in groupPrivilege.json.",
        "checks": [
            "Check user belongs to correct group",
            "Check groupPrivilege.json has View/Register/Edit/Void for this form + group",
            "Check if the entity type (subject/encounter) has correct operational types",
        ],
        "common_fixes": [
            "Add missing privilege in groupPrivilege.json",
            "Verify user is in correct group via admin panel",
            "Re-upload groupPrivilege.json with corrected permissions",
        ],
    },
    {
        "pattern": "performance",
        "keywords": [
            "slow",
            "loading",
            "hanging",
            "crash",
            "memory",
            "performance",
            "lag",
            "freeze",
            "app slow",
            "takes long",
        ],
        "diagnosis": "Performance issues on mobile are usually related to data volume.",
        "checks": [
            "Check total number of subjects synced to the device",
            "Check if any forms have too many elements (>100)",
            "Check for heavy decision rules running on every form open",
            "Check available storage on device",
        ],
        "common_fixes": [
            "Enable sync by location to reduce data on each device",
            "Optimize heavy rules (cache calculations, reduce iterations)",
            "Split large forms into multiple encounters",
            "Clear app cache and re-sync",
        ],
    },
]


def _match_patterns(text: str) -> list[tuple[dict[str, Any], float]]:
    """Score each known pattern against the input text.

    Returns a list of (pattern, score) tuples sorted by score descending.
    The score is the fraction of the pattern's keywords that appear in the
    lowercased text, with a small bonus for the pattern name itself.
    """
    text_lower = text.lower()
    scored: list[tuple[dict[str, Any], float]] = []

    for pattern in ISSUE_PATTERNS:
        hits = 0
        total = len(pattern["keywords"])
        for kw in pattern["keywords"]:
            if kw.lower() in text_lower:
                hits += 1

        # Bonus if the canonical pattern name itself appears
        if pattern["pattern"].replace("_", " ") in text_lower:
            hits += 0.5

        score = hits / max(total, 1)
        if score > 0:
            scored.append((pattern, score))

    scored.sort(key=lambda t: t[1], reverse=True)
    return scored


async def _ai_classify(
    description: str,
    error_message: str | None,
    context: str | None,
) -> dict[str, Any]:
    """Use Claude to classify an issue when keyword matching is ambiguous."""
    pattern_names = [p["pattern"] for p in ISSUE_PATTERNS]

    prompt = (
        "You are an Avni platform support expert. Classify the following "
        "support issue into one of these categories: "
        f"{', '.join(pattern_names)}.\n\n"
        f"Issue description: {description}\n"
    )
    if error_message:
        prompt += f"Error message: {error_message}\n"
    if context:
        prompt += f"Additional context: {context}\n"
    prompt += (
        "\nRespond with ONLY a JSON object (no markdown fences) with these keys:\n"
        '  "pattern": one of the category names above,\n'
        '  "confidence": a float 0-1,\n'
        '  "ai_analysis": a 2-3 sentence analysis of the issue and suggested next steps\n'
    )

    try:
        raw = await claude_client.complete(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are an Avni field data collection platform support expert. "
                "Respond only with valid JSON."
            ),
        )

        import json

        # Strip potential markdown fences
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        return json.loads(cleaned)
    except Exception:
        logger.exception("AI classification failed; falling back to keyword match")
        return {
            "pattern": "sync",
            "confidence": 0.1,
            "ai_analysis": "Could not perform AI classification. Please review the issue manually.",
        }


async def diagnose(
    description: str,
    error_message: str | None = None,
    context: str | None = None,
) -> dict[str, Any]:
    """Diagnose an Avni issue from a natural language description.

    1. Match against known patterns using keywords.
    2. If a clear match exists (confidence >= 0.3), return the structured
       diagnosis immediately.
    3. If ambiguous or no match, use Claude to classify and diagnose.

    Returns a dict with:
        pattern, diagnosis, checks, common_fixes, confidence, ai_analysis
    """
    full_text = description
    if error_message:
        full_text += " " + error_message
    if context:
        full_text += " " + context

    matches = _match_patterns(full_text)

    # Keyword match threshold -- 0.1 catches single-keyword matches
    # even without the pattern name bonus. This avoids unnecessary Claude
    # API calls for clearly classifiable issues.
    if matches and matches[0][1] >= 0.1:
        best_pattern, score = matches[0]
        return {
            "pattern": best_pattern["pattern"],
            "diagnosis": best_pattern["diagnosis"],
            "checks": best_pattern["checks"],
            "common_fixes": best_pattern["common_fixes"],
            "confidence": round(min(score, 1.0), 2),
            "ai_analysis": None,
        }

    # Weak or no keyword match -- ask Claude
    ai_result = await _ai_classify(description, error_message, context)

    # Find the pattern data for the AI-chosen category
    ai_pattern_name = ai_result.get("pattern", "sync")
    matched_pattern: dict[str, Any] | None = None
    for p in ISSUE_PATTERNS:
        if p["pattern"] == ai_pattern_name:
            matched_pattern = p
            break

    if matched_pattern is None:
        # AI returned an unknown category; default to the best keyword
        # match if any, otherwise first pattern.
        if matches:
            matched_pattern = matches[0][0]
        else:
            matched_pattern = ISSUE_PATTERNS[0]

    ai_confidence = ai_result.get("confidence", 0.5)
    # Blend keyword score if available
    keyword_score = matches[0][1] if matches else 0.0
    blended_confidence = round(max(ai_confidence, keyword_score), 2)

    return {
        "pattern": matched_pattern["pattern"],
        "diagnosis": matched_pattern["diagnosis"],
        "checks": matched_pattern["checks"],
        "common_fixes": matched_pattern["common_fixes"],
        "confidence": blended_confidence,
        "ai_analysis": ai_result.get("ai_analysis"),
    }
