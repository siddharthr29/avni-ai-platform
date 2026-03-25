"""MCP tool execution integration for chat flow.

Maps detected action intents from chat to MCP tool calls.
Supports a confirmation flow: AI suggests the action, user confirms, then MCP tool is called.
"""

import logging
from typing import Any

from app.services.mcp_client import mcp_client

logger = logging.getLogger(__name__)

# Maps action names detected in chat to MCP tool names
INTENT_TO_MCP_TOOL: dict[str, str] = {
    "create_subject_type": "create_subject_type",
    "update_subject_type": "update_subject_type",
    "delete_subject_type": "delete_subject_type",
    "create_program": "create_program",
    "create_encounter_type": "create_encounter_type",
    "create_location_type": "create_location_type",
    "create_location": "create_location",
    "create_catchment": "create_catchment",
    "find_user": "find_user",
    "update_user": "update_user",
    "delete_implementation": "delete_implementation",
}


async def check_mcp_available() -> bool:
    """Check if MCP server is available for tool execution."""
    return await mcp_client.is_available()


async def get_available_tools() -> list[dict]:
    """Get list of available MCP tools with their schemas."""
    return await mcp_client.list_tools()


async def execute_confirmed_action(
    action: str,
    params: dict[str, Any],
    auth_token: str,
) -> dict:
    """Execute an MCP tool action after user confirmation.

    Args:
        action: Action name (e.g., "create_subject_type")
        params: Parameters for the action (e.g., {"name": "Individual"})
        auth_token: Avni AUTH-TOKEN for the target organisation

    Returns:
        {"success": bool, "result": Any, "error": str | None, "action": str}
    """
    tool_name = INTENT_TO_MCP_TOOL.get(action)
    if not tool_name:
        return {
            "success": False,
            "result": None,
            "error": f"Unknown action: {action}. Available: {list(INTENT_TO_MCP_TOOL.keys())}",
            "action": action,
        }

    if not await mcp_client.is_available():
        return {
            "success": False,
            "result": None,
            "error": "MCP server is not available. Ensure avni-ai-main is running on port 8023.",
            "action": action,
        }

    # Wrap params with auth_token as MCP tools expect
    tool_args = {
        "auth_token": auth_token,
        "contract": params,
    }

    result = await mcp_client.call_tool(tool_name, tool_args)
    logger.info(
        "MCP action executed: %s → %s",
        action,
        "success" if result.get("success") else "failed",
    )

    return {**result, "action": action}


def format_action_confirmation(action: str, params: dict[str, Any]) -> str:
    """Format an action for user confirmation in chat.

    Returns a human-readable description of what the action will do.
    """
    descriptions = {
        "create_subject_type": f"Create subject type: **{params.get('name', '?')}**",
        "update_subject_type": f"Update subject type: **{params.get('name', '?')}**",
        "delete_subject_type": f"Delete subject type (ID: {params.get('id', '?')})",
        "create_program": f"Create program: **{params.get('name', '?')}**",
        "create_encounter_type": f"Create encounter type: **{params.get('name', '?')}**",
        "create_location_type": f"Create location type: **{params.get('name', '?')}** (level {params.get('level', '?')})",
        "create_location": f"Create location: **{params.get('name', '?')}**",
        "create_catchment": f"Create catchment: **{params.get('name', '?')}**",
        "find_user": f"Find user: **{params.get('name', '?')}**",
        "update_user": f"Update user: **{params.get('name', params.get('username', '?'))}**",
        "delete_implementation": "Delete implementation (metadata + admin config)",
    }

    desc = descriptions.get(action, f"Execute action: {action}")
    return f"I'd like to perform this action on your Avni organisation:\n\n{desc}\n\nShall I proceed? (yes/no)"
