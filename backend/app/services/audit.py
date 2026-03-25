"""Audit logging service.

Records all significant actions for compliance and debugging:
- Bundle generation, validation, upload
- Org connections and disconnections
- User login/logout
- MCP tool calls
- Agent executions
- Knowledge base modifications
- Permission changes

Each entry includes: who, what, when, from where, details.
"""

import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from app import db

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────────────

AUDIT_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT PRIMARY KEY,
    user_id     TEXT,
    org_id      TEXT,
    action      TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    details     JSONB DEFAULT '{}'::jsonb,
    ip_address  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_log_org_id ON audit_log(org_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log(created_at);
"""


# ── Enums ─────────────────────────────────────────────────────────────────────

class AuditAction(str, Enum):
    # Auth
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"

    # Bundle lifecycle
    BUNDLE_GENERATED = "bundle_generated"
    BUNDLE_VALIDATED = "bundle_validated"
    BUNDLE_REVIEWED = "bundle_reviewed"
    BUNDLE_UPLOADED = "bundle_uploaded"
    BUNDLE_UPLOAD_FAILED = "bundle_upload_failed"

    # Org management
    ORG_CONNECTED = "org_connected"
    ORG_DISCONNECTED = "org_disconnected"
    ORG_CONFIG_CHANGED = "org_config_changed"

    # Agent & MCP
    AGENT_TASK_STARTED = "agent_task_started"
    AGENT_TASK_COMPLETED = "agent_task_completed"
    MCP_TOOL_CALLED = "mcp_tool_called"

    # Knowledge
    KNOWLEDGE_INGESTED = "knowledge_ingested"
    KNOWLEDGE_DELETED = "knowledge_deleted"

    # Admin
    USER_ROLE_CHANGED = "user_role_changed"
    SETTINGS_CHANGED = "settings_changed"


class AuditResourceType(str, Enum):
    BUNDLE = "bundle"
    USER = "user"
    ORG = "org"
    AGENT_TASK = "agent_task"
    MCP_TOOL = "mcp_tool"
    KNOWLEDGE = "knowledge"
    SETTINGS = "settings"


# ── Schema initialisation ─────────────────────────────────────────────────────

async def init_audit_schema() -> None:
    """Create the audit_log table if it does not exist."""
    if not db._pool:
        logger.warning("DB pool not available — audit schema creation skipped")
        return
    try:
        async with db._pool.acquire() as conn:
            await conn.execute(AUDIT_SCHEMA_SQL)
        logger.info("Audit log schema ready")
    except Exception as e:
        logger.error("Failed to create audit schema: %s", e)


# ── Core functions ────────────────────────────────────────────────────────────

async def log_action(
    user_id: str | None,
    org_id: str | None,
    action: str | AuditAction,
    resource_type: str | AuditResourceType | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> dict | None:
    """Write a single audit log entry.

    Returns the created row as a dict, or None if DB is unavailable.
    """
    if not db._pool:
        logger.debug("Audit log skipped (no DB): %s %s", action, resource_id)
        return None

    entry_id = str(uuid.uuid4())
    action_str = action.value if isinstance(action, AuditAction) else action
    resource_type_str = (
        resource_type.value if isinstance(resource_type, AuditResourceType) else resource_type
    )

    try:
        async with db._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO audit_log (id, user_id, org_id, action, resource_type, resource_id, details, ip_address)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                RETURNING *
                """,
                entry_id,
                user_id,
                org_id,
                action_str,
                resource_type_str,
                resource_id,
                json.dumps(details) if details else "{}",
                ip_address,
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to write audit log: %s", e)
        return None


async def get_audit_trail(
    org_id: str,
    limit: int = 50,
    offset: int = 0,
    action_filter: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict]:
    """Query audit trail with optional filters."""
    if not db._pool:
        return []

    conditions = ["org_id = $1"]
    params: list[Any] = [org_id]
    idx = 2

    if action_filter:
        conditions.append(f"action = ${idx}")
        params.append(action_filter)
        idx += 1

    if start_date:
        conditions.append(f"created_at >= ${idx}")
        params.append(start_date)
        idx += 1

    if end_date:
        conditions.append(f"created_at <= ${idx}")
        params.append(end_date)
        idx += 1

    where = " AND ".join(conditions)
    params.extend([limit, offset])

    query = f"""
        SELECT * FROM audit_log
        WHERE {where}
        ORDER BY created_at DESC
        LIMIT ${idx} OFFSET ${idx + 1}
    """

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to query audit trail: %s", e)
        return []


async def get_user_activity(user_id: str, limit: int = 50) -> list[dict]:
    """Get recent actions performed by a specific user."""
    if not db._pool:
        return []

    try:
        async with db._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM audit_log
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error("Failed to query user activity: %s", e)
        return []


async def get_audit_summary(org_id: str, days: int = 30) -> dict[str, Any]:
    """Aggregate audit stats for an org over the given number of days."""
    if not db._pool:
        return {
            "total_actions": 0,
            "bundles_generated": 0,
            "bundles_uploaded": 0,
            "bundle_upload_failures": 0,
            "agent_tasks": 0,
            "mcp_tool_calls": 0,
            "knowledge_changes": 0,
            "unique_users": 0,
            "by_action": {},
        }

    try:
        async with db._pool.acquire() as conn:
            # Action breakdown
            rows = await conn.fetch(
                """
                SELECT action, COUNT(*) as cnt
                FROM audit_log
                WHERE org_id = $1
                  AND created_at >= now() - ($2 || ' days')::interval
                GROUP BY action
                ORDER BY cnt DESC
                """,
                org_id,
                str(days),
            )
            by_action = {r["action"]: r["cnt"] for r in rows}

            total = sum(by_action.values())
            unique_users = await conn.fetchval(
                """
                SELECT COUNT(DISTINCT user_id) FROM audit_log
                WHERE org_id = $1
                  AND created_at >= now() - ($2 || ' days')::interval
                """,
                org_id,
                str(days),
            ) or 0

            return {
                "total_actions": total,
                "bundles_generated": by_action.get(AuditAction.BUNDLE_GENERATED.value, 0),
                "bundles_uploaded": by_action.get(AuditAction.BUNDLE_UPLOADED.value, 0),
                "bundle_upload_failures": by_action.get(AuditAction.BUNDLE_UPLOAD_FAILED.value, 0),
                "agent_tasks": (
                    by_action.get(AuditAction.AGENT_TASK_STARTED.value, 0)
                    + by_action.get(AuditAction.AGENT_TASK_COMPLETED.value, 0)
                ),
                "mcp_tool_calls": by_action.get(AuditAction.MCP_TOOL_CALLED.value, 0),
                "knowledge_changes": (
                    by_action.get(AuditAction.KNOWLEDGE_INGESTED.value, 0)
                    + by_action.get(AuditAction.KNOWLEDGE_DELETED.value, 0)
                ),
                "unique_users": unique_users,
                "by_action": by_action,
            }
    except Exception as e:
        logger.error("Failed to generate audit summary: %s", e)
        return {"total_actions": 0, "error": str(e)}


# ── Context manager ───────────────────────────────────────────────────────────

@asynccontextmanager
async def audit_context(
    user_id: str,
    org_id: str,
    action_start: str | AuditAction = AuditAction.AGENT_TASK_STARTED,
    action_end: str | AuditAction = AuditAction.AGENT_TASK_COMPLETED,
    resource_type: str | AuditResourceType | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
):
    """Context manager that logs start and end of an operation.

    Usage::

        async with audit_context(user_id, org_id) as ctx:
            ctx["details"]["step"] = "processing"
            # ... do work ...

    On normal exit, logs action_end. On exception, logs action_end with error details.
    """
    ctx: dict[str, Any] = {"details": {}, "started_at": datetime.now(timezone.utc).isoformat()}

    await log_action(
        user_id=user_id,
        org_id=org_id,
        action=action_start,
        resource_type=resource_type,
        resource_id=resource_id,
        details={"started_at": ctx["started_at"]},
        ip_address=ip_address,
    )

    try:
        yield ctx
        # Success
        ctx["details"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        ctx["details"]["status"] = "success"
        await log_action(
            user_id=user_id,
            org_id=org_id,
            action=action_end,
            resource_type=resource_type,
            resource_id=resource_id,
            details=ctx["details"],
            ip_address=ip_address,
        )
    except Exception as exc:
        ctx["details"]["completed_at"] = datetime.now(timezone.utc).isoformat()
        ctx["details"]["status"] = "error"
        ctx["details"]["error"] = str(exc)
        await log_action(
            user_id=user_id,
            org_id=org_id,
            action=action_end,
            resource_type=resource_type,
            resource_id=resource_id,
            details=ctx["details"],
            ip_address=ip_address,
        )
        raise
