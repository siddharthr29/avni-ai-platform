"""MCP Client for avni-ai-main server.

Connects to the Avni MCP server (port 8023) to execute real-time
CRUD operations on Avni entities: subject types, programs, encounter types,
location types, locations, catchments, users, and implementations.

The MCP server (avni-ai-main) runs FastMCP with stateless_http=True,
exposing 20 tools via the MCP Streamable HTTP transport at /mcp/.
It also exposes custom REST endpoints:
  - GET  /health                           — health check
  - POST /process-config-async             — multi-tool orchestrated CRUD
  - GET  /process-config-status/{task_id}  — check task progress

This client wraps both the MCP JSON-RPC protocol (for tool listing/calling)
and the custom REST endpoints (for config processing).
"""

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

MCP_BASE_URL = getattr(settings, "MCP_SERVER_URL", "http://localhost:8023")
MCP_TIMEOUT = 30.0


class MCPClient:
    """Client for the Avni MCP server (avni-ai-main).

    Supports two modes:
    1. MCP protocol (JSON-RPC via /mcp/) for listing and calling individual tools
    2. Custom REST endpoints for health checks and config processing
    """

    def __init__(self, base_url: str = MCP_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._available_tools: list[dict] | None = None

    # ── Health & connectivity ──────────────────────────────────────────────

    async def is_available(self) -> bool:
        """Check if the MCP server is reachable via its /health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False

    # ── MCP protocol: tools/list ───────────────────────────────────────────

    async def list_tools(self) -> list[dict]:
        """List all available MCP tools via the MCP JSON-RPC protocol.

        Sends a JSON-RPC request to the /mcp/ endpoint with method "tools/list".
        Results are cached after the first successful call.
        """
        if self._available_tools is not None:
            return self._available_tools
        try:
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {},
                    },
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # MCP response: {"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}
                    result = data.get("result", {})
                    tools = result.get("tools", [])
                    if tools:
                        self._available_tools = tools
                        logger.info("MCP server: %d tools available", len(tools))
                    return tools
                else:
                    logger.warning(
                        "MCP tools/list returned HTTP %d: %s",
                        resp.status_code,
                        resp.text[:200],
                    )
        except Exception as e:
            logger.warning("MCP server unavailable for tools/list: %s", e)
        return []

    def clear_tools_cache(self) -> None:
        """Clear the cached tools list (e.g. after server restart)."""
        self._available_tools = None

    # ── MCP protocol: tools/call ───────────────────────────────────────────

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """Call a specific MCP tool via the MCP JSON-RPC protocol.

        Sends a JSON-RPC request to /mcp/ with method "tools/call".

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        try:
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
                resp = await client.post(
                    f"{self.base_url}/mcp/",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": tool_name,
                            "arguments": arguments,
                        },
                    },
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if "error" in data:
                        return {
                            "success": False,
                            "result": None,
                            "error": f"MCP error: {data['error']}",
                        }
                    return {
                        "success": True,
                        "result": data.get("result"),
                        "error": None,
                    }
                else:
                    return {
                        "success": False,
                        "result": None,
                        "error": f"MCP tool error (HTTP {resp.status_code}): {resp.text[:300]}",
                    }
        except httpx.TimeoutException:
            return {"success": False, "result": None, "error": "MCP server timeout"}
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    # ── Custom REST: config processing ─────────────────────────────────────

    async def process_config(
        self, config_data: dict, auth_token: str
    ) -> dict:
        """Use the config processor for multi-tool orchestrated CRUD execution.

        This is the high-level endpoint that takes a structured config dict
        with create/update/delete operations and executes them via the MCP
        server's task manager (which calls multiple tools in sequence).

        Args:
            config_data: Dict with "create", "update", "delete" keys containing
                entity arrays (subjectTypes, programs, encounterTypes, etc.)
            auth_token: Avni AUTH-TOKEN for the target organisation.

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{self.base_url}/process-config-async",
                    json={"configuration": {"config": config_data}},
                    headers={
                        "Content-Type": "application/json",
                        "avni-auth-token": auth_token,
                    },
                )
                if resp.status_code == 200:
                    return {"success": True, "result": resp.json(), "error": None}
                else:
                    return {
                        "success": False,
                        "result": None,
                        "error": f"Config processor error (HTTP {resp.status_code}): {resp.text[:300]}",
                    }
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    async def get_config_status(self, task_id: str) -> dict:
        """Check the status of an async config processing task.

        Returns:
            {"success": bool, "result": Any, "error": str | None}
        """
        try:
            async with httpx.AsyncClient(timeout=MCP_TIMEOUT) as client:
                resp = await client.get(
                    f"{self.base_url}/process-config-status/{task_id}",
                )
                if resp.status_code == 200:
                    return {"success": True, "result": resp.json(), "error": None}
                elif resp.status_code == 404:
                    return {
                        "success": False,
                        "result": None,
                        "error": f"Task {task_id} not found or expired",
                    }
                else:
                    return {
                        "success": False,
                        "result": None,
                        "error": f"Status check error (HTTP {resp.status_code}): {resp.text[:300]}",
                    }
        except Exception as e:
            return {"success": False, "result": None, "error": str(e)}

    # ── Convenience methods for common tool calls ──────────────────────────

    async def create_subject_type(self, auth_token: str, name: str, **kwargs) -> dict:
        return await self.call_tool(
            "create_subject_type",
            {"auth_token": auth_token, "contract": {"name": name, **kwargs}},
        )

    async def update_subject_type(self, auth_token: str, **kwargs) -> dict:
        return await self.call_tool(
            "update_subject_type",
            {"auth_token": auth_token, "contract": kwargs},
        )

    async def delete_subject_type(self, auth_token: str, id: int) -> dict:
        return await self.call_tool(
            "delete_subject_type",
            {"auth_token": auth_token, "contract": {"id": id}},
        )

    async def create_program(self, auth_token: str, name: str, **kwargs) -> dict:
        return await self.call_tool(
            "create_program",
            {"auth_token": auth_token, "contract": {"name": name, **kwargs}},
        )

    async def create_encounter_type(self, auth_token: str, name: str, **kwargs) -> dict:
        return await self.call_tool(
            "create_encounter_type",
            {"auth_token": auth_token, "contract": {"name": name, **kwargs}},
        )

    async def create_location_type(self, auth_token: str, name: str, level: float, **kwargs) -> dict:
        return await self.call_tool(
            "create_location_type",
            {"auth_token": auth_token, "contract": {"name": name, "level": level, **kwargs}},
        )

    async def create_location(self, auth_token: str, name: str, **kwargs) -> dict:
        return await self.call_tool(
            "create_location",
            {"auth_token": auth_token, "contract": {"name": name, **kwargs}},
        )

    async def create_catchment(self, auth_token: str, name: str, **kwargs) -> dict:
        return await self.call_tool(
            "create_catchment",
            {"auth_token": auth_token, "contract": {"name": name, **kwargs}},
        )

    async def find_user(self, auth_token: str, name: str) -> dict:
        return await self.call_tool(
            "find_user",
            {"auth_token": auth_token, "contract": {"name": name}},
        )

    async def update_user(self, auth_token: str, **kwargs) -> dict:
        return await self.call_tool(
            "update_user",
            {"auth_token": auth_token, "contract": kwargs},
        )

    async def delete_implementation(
        self,
        auth_token: str,
        delete_metadata: bool = True,
        delete_admin_config: bool = True,
    ) -> dict:
        return await self.call_tool(
            "delete_implementation",
            {
                "auth_token": auth_token,
                "contract": {
                    "deleteMetadata": delete_metadata,
                    "deleteAdminConfig": delete_admin_config,
                },
            },
        )


# Singleton
mcp_client = MCPClient()
