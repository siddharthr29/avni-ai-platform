"""Bundle editor router — natural language edits to generated bundles.

Provides endpoints for editing bundle files using natural language instructions
instead of manual JSON manipulation. Integrates with the existing bundle
generation and review workflow.
"""

import logging

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

from app.routers.bundle import verify_bundle_lock_ownership
from app.services.bundle_editor import (
    BundleEditCommand,
    apply_edit,
    edit_bundle_nl,
    parse_edit_command,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class NLEditRequest(BaseModel):
    instruction: str = Field(
        ...,
        description="Natural language instruction, e.g. \"rename field 'Weight' to 'Body Weight'\"",
        min_length=3,
        max_length=2000,
    )
    user_id: str | None = Field(
        default=None,
        description="User ID for lock ownership verification",
    )


class StructuredEditRequest(BaseModel):
    action: str = Field(
        ...,
        description="Edit action: rename_field, add_field, remove_field, make_mandatory, make_optional, change_type, add_option, remove_option",
    )
    target_field: str = Field(..., description="Field/concept name to modify")
    target_form: str | None = Field(
        default=None,
        description="Specific form name, or null for all forms",
    )
    params: dict = Field(
        default_factory=dict,
        description="Action-specific parameters (e.g. new_name, data_type, options)",
    )
    user_id: str | None = Field(
        default=None,
        description="User ID for lock ownership verification",
    )


class ParseRequest(BaseModel):
    instruction: str = Field(
        ...,
        description="Natural language instruction to parse into structured commands",
        min_length=3,
        max_length=2000,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/bundle/{bundle_id}/edit-nl")
async def edit_bundle_natural_language(
    bundle_id: str,
    request: NLEditRequest,
) -> dict:
    """Edit a bundle using a natural language instruction.

    Parses the instruction into structured edit commands, applies them to
    the bundle files on disk, and returns a summary of all changes made.

    If the bundle is locked by another user, the request is rejected with 409.
    Pass user_id in the body to identify yourself as the lock owner.

    Examples:
        - "rename field 'Weight' to 'Body Weight'"
        - "add field 'Blood Group' with options A+, A-, B+, B-, O+, O-, AB+, AB-"
        - "remove field 'Caste'"
        - "make 'Phone Number' mandatory"
        - "change data type of 'Age' to Numeric"
        - "add option 'Other' to 'Referral Reason'"
    """
    if request.user_id:
        await verify_bundle_lock_ownership(bundle_id, request.user_id)

    result = await edit_bundle_nl(bundle_id, request.instruction)

    if not result["success"] and result.get("errors"):
        # If the bundle wasn't found at all, return 404
        if any("not found" in e.lower() for e in result["errors"]):
            if any("bundle" in e.lower() for e in result["errors"]):
                raise HTTPException(status_code=404, detail=result["errors"][0])

    return result


@router.post("/bundle/{bundle_id}/edit-structured")
async def edit_bundle_structured(
    bundle_id: str,
    request: StructuredEditRequest,
) -> dict:
    """Edit a bundle using a structured command (no LLM parsing needed).

    Use this when you already have the parsed command structure, e.g. from
    a UI that builds the command programmatically.

    If the bundle is locked by another user, the request is rejected with 409.
    Pass user_id in the body to identify yourself as the lock owner.
    """
    if request.user_id:
        await verify_bundle_lock_ownership(bundle_id, request.user_id)

    command = BundleEditCommand(
        action=request.action,
        target_field=request.target_field,
        target_form=request.target_form,
        params=request.params,
    )

    result = apply_edit(bundle_id, command)

    if not result.get("success"):
        error = result.get("error", "Unknown error")
        if "not found" in error.lower() and "bundle" in error.lower():
            raise HTTPException(status_code=404, detail=error)

    return {
        "success": result.get("success", False),
        "bundle_id": bundle_id,
        "command": {
            "action": command.action,
            "description": command.describe(),
        },
        "changes": result.get("changes", []),
        "error": result.get("error"),
    }


@router.post("/bundle/edit/parse")
async def parse_edit_instruction(request: ParseRequest) -> dict:
    """Parse a natural language instruction into structured commands (dry run).

    Returns the parsed commands without applying them. Useful for previewing
    what changes would be made before committing.
    """
    try:
        commands = await parse_edit_command(request.instruction)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "instruction": request.instruction,
        "commands": [
            {
                "action": cmd.action,
                "target_field": cmd.target_field,
                "target_form": cmd.target_form,
                "params": cmd.params,
                "description": cmd.describe(),
            }
            for cmd in commands
        ],
    }
