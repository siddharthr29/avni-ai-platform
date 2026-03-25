"""Action detection and confirmed action execution.

Detects user intent to perform actions (bundle create, org setup, corrections,
MCP calls, bundle regeneration) via regex patterns, and executes confirmed actions.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Action patterns detected in user messages
_BUNDLE_ACTION_PATTERNS = [
    r"\b(create|generate|build|make)\b.*\bbundle\b",
    r"\bbundle\b.*\b(create|generate|build|make)\b",
    r"\bgenerate\b.*\b(concepts|forms|form mappings)\b",
    r"\bconvert\b.*\bsrs\b.*\bbundle\b",
]

_ORG_ACTION_PATTERNS = [
    r"\b(create|setup|set up)\b.*\b(org|organisation|organization)\b",
    r"\b(apply|upload|deploy)\b.*\bbundle\b",
]

_BUNDLE_CORRECT_PATTERNS = [
    r"\b(change|fix|correct|update|modify|rename|replace)\b.*\b(bundle|form|field|subject|program|encounter|visit)\b",
    r"\b(should be|instead of|not|wrong|incorrect)\b.*\b(form|field|subject|program|encounter|visit|monthly|weekly|daily)\b",
    r"\b(add|remove|delete)\b.*\b(field|form|skip logic|option|rule)\b",
    r"\bregenerate\b.*\bbundle\b",
]

_BUNDLE_ERROR_PATTERNS = [
    r"\b(upload|import)\s+(failed|error|errors)\b",
    r"\berror[s]?\s*:?\s*(Concept|Duplicate|Invalid|not found|already exists)\b",
    r"\bhere.s the error\b",
    r"\bfix\s+(this|these)\s+error",
    r"\bfailed.*upload.*error",
]

_MCP_ACTION_PATTERNS = [
    r"\b(create|update|delete)\b.*\b(subject type|program|encounter type|location)\b",
    r"\b(call|execute|run)\b.*\b(mcp|tool)\b",
]


def detect_action(message: str) -> str | None:
    """Detect if the user is requesting an action (bundle creation, org setup, MCP call)."""
    msg_lower = message.lower()
    for pattern in _BUNDLE_ACTION_PATTERNS:
        if re.search(pattern, msg_lower):
            return "bundle_create"
    for pattern in _ORG_ACTION_PATTERNS:
        if re.search(pattern, msg_lower):
            return "org_setup"
    # Check for error-based regeneration before general corrections
    for pattern in _BUNDLE_ERROR_PATTERNS:
        if re.search(pattern, msg_lower):
            return "bundle_regenerate"
    for pattern in _BUNDLE_CORRECT_PATTERNS:
        if re.search(pattern, msg_lower):
            return "bundle_correct"
    for pattern in _MCP_ACTION_PATTERNS:
        if re.search(pattern, msg_lower):
            return "mcp_call"
    return None


async def execute_confirmed_action(action: dict) -> str:
    """Execute a confirmed action."""
    action_type = action.get("action_type", "")

    if action_type == "bundle_upload":
        from app.services.avni_org_service import avni_org_service
        from app.services.bundle_generator import get_bundle_zip_path

        bundle_id = action.get("bundle_id", "")
        auth_token = action.get("auth_token", "")
        zip_path = get_bundle_zip_path(bundle_id)
        if zip_path:
            result = await avni_org_service.upload_bundle_two_pass(
                auth_token=auth_token,
                bundle_zip_path=zip_path,
            )
            return f"Bundle uploaded: {result.get('message', '')}"
        return "Bundle not found"

    elif action_type == "mcp_call":
        from app.services.mcp_client import mcp_client

        tool_name = action.get("tool_name", "")
        arguments = action.get("arguments", {})
        result = await mcp_client.call_tool(tool_name, arguments)
        if result["success"]:
            return f"MCP tool '{tool_name}' executed successfully"
        return f"MCP tool failed: {result.get('error', '')}"

    elif action_type == "agent_run":
        from app.services.react_agent import react_agent

        task_id = action.get("task_id", "")
        goal = action.get("goal", "")
        auth_token = action.get("auth_token", "")
        task = await react_agent.run(task_id, goal, auth_token)
        return f"Agent task {task.status}: {len(task.steps)} steps"

    return "Unknown action type"
