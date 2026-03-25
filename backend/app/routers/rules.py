"""API endpoints for Avni rule generation, testing, and template browsing."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import (
    RuleGenerateRequest,
    RuleGenerateResponse,
    RuleTemplateSummary,
    RuleTestRequest,
    RuleTestResponse,
    RuleValidateRequest,
)
from app.services.rule_generator import (
    RULE_TEMPLATES,
    find_matching_templates,
    generate_rule,
    get_template_by_id,
    test_rule,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/rules/generate", response_model=RuleGenerateResponse)
async def generate_rule_endpoint(request: RuleGenerateRequest) -> RuleGenerateResponse:
    """Generate an Avni rule from a natural language description.

    Provide a description of the desired rule behaviour and optionally the
    form JSON and concepts list for accurate UUID references.  The engine
    selects matching templates as few-shot examples and uses Claude to
    produce the final rule code.
    """
    if not request.description or not request.description.strip():
        raise HTTPException(status_code=400, detail="description must not be empty")

    valid_types = {
        "ViewFilter", "Decision", "VisitSchedule", "Validation",
        "Checklist", "EnrolmentSummary", "Eligibility",
    }
    if request.rule_type and request.rule_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid rule_type '{request.rule_type}'. Must be one of: {', '.join(sorted(valid_types))}",
        )

    try:
        result = await generate_rule(
            description=request.description,
            rule_type=request.rule_type,
            form_json=request.form_json,
            concepts_json=request.concepts_json,
            complexity_hint=request.complexity_hint,
        )
    except Exception as e:
        logger.exception("Rule generation failed")
        raise HTTPException(status_code=500, detail=f"Rule generation failed: {str(e)}")

    return RuleGenerateResponse(
        code=result["code"],
        rule_type=result["type"],
        format=result["format"],
        confidence=result["confidence"],
        explanation=result["explanation"],
        warnings=result["warnings"],
        template_used=result.get("template_used"),
    )


@router.post("/rules/test", response_model=RuleTestResponse)
async def test_rule_endpoint(request: RuleTestRequest) -> RuleTestResponse:
    """Validate an Avni rule for syntax correctness and concept references.

    Provide the rule code and type.  Optionally pass a concepts list so the
    engine can cross-check that all referenced concept names actually exist.
    """
    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="code must not be empty")

    try:
        result = await test_rule(
            code=request.code,
            rule_type=request.rule_type,
            concepts=request.concepts,
        )
    except Exception as e:
        logger.exception("Rule testing failed")
        raise HTTPException(status_code=500, detail=f"Rule testing failed: {str(e)}")

    return RuleTestResponse(
        valid=result["valid"],
        syntax_ok=result["syntax_ok"],
        concept_refs_ok=result["concept_refs_ok"],
        warnings=result["warnings"],
        errors=result["errors"],
    )


@router.post("/rules/validate")
async def validate_rule(request: RuleValidateRequest) -> dict:
    """Validate a JavaScript rule against Avni patterns.

    Checks syntax (balanced delimiters), forbidden patterns (eval, require,
    fetch, etc.), Avni import usage, rule-type consistency, UUID format,
    and common authoring mistakes — all without executing the code.
    """
    from app.services.rule_validator import validate_rule_js

    if not request.code or not request.code.strip():
        raise HTTPException(status_code=400, detail="code must not be empty")

    return validate_rule_js(request.code, request.rule_type)


@router.get("/rules/templates", response_model=list[RuleTemplateSummary])
async def list_templates(
    type: str | None = Query(default=None, description="Filter by rule type"),
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of templates to return"),
) -> list[RuleTemplateSummary]:
    """List available rule templates, optionally filtered by type."""
    templates = RULE_TEMPLATES

    if type:
        templates = [t for t in templates if t["type"].lower() == type.lower()]

    templates = templates[:limit]

    return [
        RuleTemplateSummary(
            id=t["id"],
            name=t["name"],
            type=t["type"],
            description=t["description"],
            complexity=t["complexity"],
            format=t["format"],
            sectors=t["sectors"],
        )
        for t in templates
    ]


@router.get("/rules/templates/{template_id}")
async def get_template(template_id: str) -> dict:
    """Get a specific rule template with full code, example, and parameters."""
    template = get_template_by_id(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return template
