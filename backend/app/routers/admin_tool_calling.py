"""Admin endpoints for MCP tool-calling settings."""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app import db
from app.routers.admin import _require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/settings/tool-calling", tags=["Admin Tool Calling"])


class ToolCallingSetting(BaseModel):
    tool_name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    model_override: str | None = None
    config: dict = Field(default_factory=dict)


class ToolCallingSettingResponse(ToolCallingSetting):
    id: str
    org_id: str


@router.get("", response_model=list[ToolCallingSettingResponse])
async def list_tool_calling_settings(request: Request):
    """List all tool-calling settings for the admin's org."""
    user_id, role, org_name = _require_admin(request)
    org_id = org_name or ""
    if not db._pool:
        return []
    async with db._pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, org_id, tool_name, enabled, model_override, config "
            "FROM tool_calling_settings WHERE org_id = $1 ORDER BY tool_name",
            org_id,
        )
    return [
        ToolCallingSettingResponse(
            id=r["id"], org_id=r["org_id"], tool_name=r["tool_name"],
            enabled=r["enabled"], model_override=r["model_override"],
            config=dict(r["config"]) if r["config"] else {},
        )
        for r in rows
    ]


@router.post("", response_model=ToolCallingSettingResponse, status_code=201)
async def create_tool_calling_setting(request: Request, body: ToolCallingSetting):
    """Create or update a tool-calling setting."""
    user_id, role, org_name = _require_admin(request)
    org_id = org_name or ""
    if not db._pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    import json
    async with db._pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tool_calling_settings (org_id, tool_name, enabled, model_override, config)
               VALUES ($1, $2, $3, $4, $5::jsonb)
               ON CONFLICT (org_id, tool_name) DO UPDATE SET
                   enabled = EXCLUDED.enabled,
                   model_override = EXCLUDED.model_override,
                   config = EXCLUDED.config,
                   updated_at = now()
               RETURNING id, org_id, tool_name, enabled, model_override, config""",
            org_id, body.tool_name, body.enabled, body.model_override,
            json.dumps(body.config),
        )
    return ToolCallingSettingResponse(
        id=row["id"], org_id=row["org_id"], tool_name=row["tool_name"],
        enabled=row["enabled"], model_override=row["model_override"],
        config=dict(row["config"]) if row["config"] else {},
    )


@router.delete("/{tool_name}", status_code=204)
async def delete_tool_calling_setting(request: Request, tool_name: str):
    """Delete a tool-calling setting."""
    user_id, role, org_name = _require_admin(request)
    org_id = org_name or ""
    if not db._pool:
        raise HTTPException(status_code=503, detail="Database unavailable")
    async with db._pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM tool_calling_settings WHERE org_id = $1 AND tool_name = $2",
            org_id, tool_name,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Setting not found")
