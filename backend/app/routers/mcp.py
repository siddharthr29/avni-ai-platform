"""MCP Server integration endpoints.

Exposes the avni-ai-main MCP server tools through our API,
with access to all 20 CRUD tools for Avni entities (subject types,
programs, encounter types, location types, locations, catchments,
users, implementations).

Endpoints:
  GET  /api/mcp/status          — MCP server health + tool count
  GET  /api/mcp/tools           — list all tools with their schemas
  POST /api/mcp/call            — call a specific MCP tool
  POST /api/mcp/process-config  — multi-tool orchestrated CRUD
  GET  /api/mcp/config-status/{task_id} — check config task progress
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.mcp_client import mcp_client

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request models ─────────────────────────────────────────────────────────


class MCPToolCallRequest(BaseModel):
    tool_name: str = Field(description="Name of the MCP tool to call")
    arguments: dict = Field(default_factory=dict, description="Tool arguments")


class MCPConfigRequest(BaseModel):
    config_data: dict = Field(
        description=(
            "Structured config with create/update/delete keys, each containing "
            "entity arrays: subjectTypes, programs, encounterTypes, "
            "addressLevelTypes, locations, catchments"
        )
    )
    auth_token: str = Field(description="Avni AUTH-TOKEN for the target organisation")
    org_type: str = Field(
        default="Trial",
        description="Organisation type: Trial, Production, or UAT. "
        "Config processing is blocked for Production and UAT.",
    )


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/mcp/status")
async def mcp_status() -> dict:
    """Check if the MCP server is available and list tool names."""
    available = await mcp_client.is_available()
    tools = await mcp_client.list_tools() if available else []
    return {
        "available": available,
        "server_url": mcp_client.base_url,
        "tool_count": len(tools),
        "tools": [t.get("name", "") for t in tools] if tools else [],
    }


@router.get("/mcp/tools")
async def list_mcp_tools() -> dict:
    """List all available MCP tools with their input schemas."""
    tools = await mcp_client.list_tools()
    if not tools:
        raise HTTPException(status_code=503, detail="MCP server unavailable or returned no tools")
    return {"tools": tools}


@router.post("/mcp/call")
async def call_mcp_tool(request: MCPToolCallRequest) -> dict:
    """Call a specific MCP tool by name with arguments.

    CAUTION: Write operations (create/update/delete) modify the Avni org.
    Use the confirm_action SSE event in chat for human-in-the-loop approval.

    Tool names follow the pattern: create_subject_type, update_program,
    delete_encounter_type, find_user, get_locations, etc.
    """
    if not await mcp_client.is_available():
        raise HTTPException(status_code=503, detail="MCP server unavailable")

    result = await mcp_client.call_tool(request.tool_name, request.arguments)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/mcp/process-config")
async def process_config(request: MCPConfigRequest) -> dict:
    """Process a structured CRUD config via the MCP server's multi-tool orchestrator.

    This takes a config dict like:
    {
        "create": {
            "subjectTypes": [{"name": "Beneficiary", ...}],
            "programs": [{"name": "Maternal Health", ...}],
            "encounterTypes": [{"name": "ANC Visit", ...}]
        }
    }
    and executes the necessary MCP tool calls to set it up in Avni.

    The processing runs asynchronously on the MCP server. Use the returned
    task_id with /mcp/config-status/{task_id} to check progress.
    """
    if not await mcp_client.is_available():
        raise HTTPException(status_code=503, detail="MCP server unavailable")

    # Inject org_type into config_data for server-side validation
    config_data = request.config_data.copy()
    config_data["org_type"] = request.org_type

    result = await mcp_client.process_config(config_data, request.auth_token)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/mcp/config-status/{task_id}")
async def config_task_status(task_id: str) -> dict:
    """Check the status of an async config processing task."""
    if not await mcp_client.is_available():
        raise HTTPException(status_code=503, detail="MCP server unavailable")

    result = await mcp_client.get_config_status(task_id)
    if not result["success"]:
        status_code = 404 if "not found" in (result["error"] or "") else 400
        raise HTTPException(status_code=status_code, detail=result["error"])
    return result
