"""Personalization service.

Manages:
1. Custom instructions injection into system prompts
2. Org memory extraction from bundles
3. Context-aware suggested prompts
4. Chat history search and export
"""

import json
import logging
from datetime import datetime
from typing import Any

from app.services.org_memory import get_org_context_prompt, get_all_memories

logger = logging.getLogger(__name__)

# Schema for personalization tables — executed during init
PERSONALIZATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id         TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme           TEXT NOT NULL DEFAULT 'system',
    language        TEXT NOT NULL DEFAULT 'en',
    default_view    TEXT NOT NULL DEFAULT 'chat',
    custom_instructions TEXT NOT NULL DEFAULT '',
    preferences     JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saved_prompts (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           TEXT NOT NULL,
    prompt_text     TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'general',
    pinned          BOOLEAN NOT NULL DEFAULT false,
    use_count       INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_saved_prompts_user_id ON saved_prompts(user_id);

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_messages_fts ON messages USING gin(to_tsvector('english', content));
"""

# Role-based suggested prompts
ROLE_PROMPTS: dict[str, list[dict[str, str]]] = {
    "ngo_user": [
        {"title": "Register beneficiary", "prompt": "How do I register a new beneficiary?"},
        {"title": "Sync troubleshooting", "prompt": "Why is sync failing?"},
        {"title": "Export data", "prompt": "How to export data?"},
        {"title": "Schedule a visit", "prompt": "How do I schedule a follow-up visit?"},
        {"title": "View dashboard", "prompt": "Show me the dashboard for my catchment area"},
        {"title": "Reset password", "prompt": "How do I reset a field worker's password?"},
    ],
    "implementor": [
        {"title": "Generate bundle", "prompt": "Generate a bundle from this SRS"},
        {"title": "Write skip logic", "prompt": "Help me write a skip logic rule"},
        {"title": "Review form design", "prompt": "Review my form design"},
        {"title": "Create encounter type", "prompt": "Create a new encounter type for monthly visits"},
        {"title": "Concept modelling", "prompt": "Help me model concepts for a nutrition program"},
        {"title": "Visit scheduling rule", "prompt": "Write a visit scheduling rule for quarterly checkups"},
    ],
    "org_admin": [
        {"title": "Upload bundle", "prompt": "Upload bundle to our staging org"},
        {"title": "Usage stats", "prompt": "Show usage stats"},
        {"title": "Run agent", "prompt": "Run the agent to create subject types"},
        {"title": "Compare bundles", "prompt": "Compare my bundle against the current org configuration"},
        {"title": "User management", "prompt": "How to add a new user to our organisation?"},
        {"title": "Template org", "prompt": "Apply a template organisation to our setup"},
    ],
}

# Intent-based follow-up prompts (shown after detecting recent intents)
INTENT_FOLLOWUPS: dict[str, list[dict[str, str]]] = {
    "bundle": [
        {"title": "Review bundle", "prompt": "Review the generated bundle for issues"},
        {"title": "Upload to staging", "prompt": "Upload this bundle to our staging org"},
        {"title": "Compare changes", "prompt": "Compare this bundle with what's currently on the server"},
    ],
    "rule": [
        {"title": "Test rule", "prompt": "Test this rule with sample data"},
        {"title": "Add validation", "prompt": "Add a validation rule for this form"},
        {"title": "Schedule visits", "prompt": "Write a visit scheduling rule"},
    ],
    "support": [
        {"title": "Check sync status", "prompt": "Check sync status for all users"},
        {"title": "View error logs", "prompt": "Show recent error logs"},
    ],
}


def _get_pool():
    """Get the database pool, returning None if unavailable."""
    try:
        from app.db import _pool
        return _pool
    except Exception:
        return None


async def ensure_schema() -> None:
    """Create the personalization tables if they don't exist."""
    pool = _get_pool()
    if not pool:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(PERSONALIZATION_SCHEMA_SQL)
        logger.info("Personalization schema ready")
    except Exception as e:
        logger.error("Failed to create personalization schema: %s", e)


async def get_personalized_system_prompt(user_id: str, base_prompt: str) -> str:
    """Append custom instructions and org memory to a system prompt.

    Args:
        user_id: The user's ID.
        base_prompt: The base system prompt to augment.

    Returns:
        The augmented system prompt with custom instructions and org context appended.
    """
    pool = _get_pool()
    if not pool:
        return base_prompt

    parts = [base_prompt]

    # Fetch custom instructions
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT custom_instructions FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            if row and row["custom_instructions"]:
                parts.append(
                    f"\n## User's Custom Instructions\n{row['custom_instructions']}"
                )
    except Exception as e:
        logger.warning("Failed to fetch custom instructions for user %s: %s", user_id, e)

    # Fetch org memory — need to find the user's org
    try:
        async with pool.acquire() as conn:
            user_row = await conn.fetchrow(
                "SELECT org_name FROM users WHERE id = $1",
                user_id,
            )
            if user_row and user_row["org_name"]:
                org_context = await get_org_context_prompt(user_row["org_name"])
                if org_context:
                    parts.append(org_context)
    except Exception as e:
        logger.warning("Failed to fetch org context for user %s: %s", user_id, e)

    return "\n".join(parts)


async def extract_org_memory_from_bundle(org_id: str, bundle_data: dict) -> dict[str, int]:
    """Parse subject types, programs, concepts from a generated bundle
    and store in org_memory table.

    Args:
        org_id: The organisation identifier.
        bundle_data: Dict of bundle file contents keyed by filename.

    Returns:
        Counts of extracted entities per type.
    """
    from app.services.org_memory import learn_from_bundle
    return await learn_from_bundle(org_id, bundle_data)


async def get_suggested_prompts(
    user_id: str,
    role: str | None = None,
    recent_intents: list[str] | None = None,
) -> list[dict[str, str]]:
    """Return 4-6 contextual prompt suggestions based on role and recent activity.

    Args:
        user_id: The user's ID.
        role: User role — 'ngo_user', 'implementor', or 'org_admin'.
        recent_intents: List of recent intent types from user's chat history.

    Returns:
        List of prompt suggestion dicts with 'title' and 'prompt' keys.
    """
    suggestions: list[dict[str, str]] = []

    # 1. Add intent-based follow-ups first (most contextual)
    if recent_intents:
        for intent in recent_intents[:2]:
            followups = INTENT_FOLLOWUPS.get(intent, [])
            for fp in followups[:2]:
                if fp not in suggestions:
                    suggestions.append(fp)

    # 2. Add role-based prompts
    effective_role = role or "implementor"
    role_suggestions = ROLE_PROMPTS.get(effective_role, ROLE_PROMPTS["implementor"])
    for rp in role_suggestions:
        if len(suggestions) >= 6:
            break
        if rp not in suggestions:
            suggestions.append(rp)

    # 3. Add from most-used saved prompts
    pool = _get_pool()
    if pool and len(suggestions) < 6:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT title, prompt_text FROM saved_prompts
                    WHERE user_id = $1 AND pinned = true
                    ORDER BY use_count DESC
                    LIMIT 2
                    """,
                    user_id,
                )
                for row in rows:
                    if len(suggestions) >= 6:
                        break
                    suggestions.append({
                        "title": row["title"],
                        "prompt": row["prompt_text"],
                        "source": "saved",
                    })
        except Exception:
            pass

    return suggestions[:6]


async def search_chat_history(
    user_id: str,
    query: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Full-text search across all messages in a user's chat sessions.

    Uses PostgreSQL ts_vector for efficient full-text search.

    Args:
        user_id: The user's ID.
        query: Search query string.
        limit: Maximum number of results.

    Returns:
        List of matching messages with session context.
    """
    pool = _get_pool()
    if not pool:
        return []

    try:
        # Sanitize query for tsquery — replace special chars
        safe_query = " & ".join(
            word for word in query.split() if word.strip()
        )
        if not safe_query:
            return []

        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.session_id, m.role, m.content, m.created_at,
                       s.title as session_title,
                       ts_rank(to_tsvector('english', m.content), plainto_tsquery('english', $2)) as rank
                FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = $1
                  AND to_tsvector('english', m.content) @@ plainto_tsquery('english', $2)
                ORDER BY rank DESC, m.created_at DESC
                LIMIT $3
                """,
                user_id, query, limit,
            )
            return [
                {
                    "id": row["id"],
                    "session_id": row["session_id"],
                    "session_title": row["session_title"],
                    "role": row["role"],
                    "content": row["content"][:300],  # Truncate for preview
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "rank": float(row["rank"]),
                }
                for row in rows
            ]
    except Exception as e:
        logger.error("Chat history search failed for user %s: %s", user_id, e)
        return []


async def export_chat_as_markdown(session_id: str) -> str:
    """Export an entire chat session as formatted markdown.

    Args:
        session_id: The session ID to export.

    Returns:
        Formatted markdown string of the conversation.
    """
    pool = _get_pool()
    if not pool:
        return "# Chat Export\n\n_Database not connected._"

    try:
        async with pool.acquire() as conn:
            # Get session info
            session = await conn.fetchrow(
                "SELECT s.title, s.created_at, u.name as user_name, u.org_name "
                "FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.id = $1",
                session_id,
            )
            if not session:
                return f"# Chat Export\n\n_Session {session_id} not found._"

            # Get all messages
            messages = await conn.fetch(
                "SELECT role, content, created_at FROM messages WHERE session_id = $1 ORDER BY created_at ASC",
                session_id,
            )

        # Build markdown
        lines: list[str] = [
            f"# {session['title']}",
            "",
            f"**User:** {session['user_name']}  ",
            f"**Organisation:** {session['org_name']}  ",
            f"**Date:** {session['created_at'].strftime('%Y-%m-%d %H:%M') if session['created_at'] else 'Unknown'}  ",
            f"**Messages:** {len(messages)}",
            "",
            "---",
            "",
        ]

        for msg in messages:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            if msg["role"] == "system":
                role_label = "System"

            timestamp = ""
            if msg["created_at"]:
                timestamp = f" _{msg['created_at'].strftime('%H:%M')}_"

            lines.append(f"### {role_label}{timestamp}")
            lines.append("")
            lines.append(msg["content"])
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.error("Failed to export chat session %s: %s", session_id, e)
        return f"# Chat Export\n\n_Export failed: {e}_"


async def get_user_context(user_id: str) -> dict[str, Any]:
    """Return combined user preferences, org memory, and recent activity summary.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with 'preferences', 'org_memory', 'recent_activity' keys.
    """
    pool = _get_pool()
    if not pool:
        return {
            "preferences": _default_preferences(),
            "org_memory": {},
            "recent_activity": {},
        }

    context: dict[str, Any] = {}

    try:
        async with pool.acquire() as conn:
            # User preferences
            pref_row = await conn.fetchrow(
                "SELECT * FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            if pref_row:
                context["preferences"] = {
                    "theme": pref_row["theme"],
                    "language": pref_row["language"],
                    "default_view": pref_row["default_view"],
                    "custom_instructions": pref_row["custom_instructions"],
                    "extra": pref_row["preferences"] if isinstance(pref_row["preferences"], dict) else json.loads(pref_row["preferences"]),
                }
            else:
                context["preferences"] = _default_preferences()

            # User info for org lookup
            user_row = await conn.fetchrow(
                "SELECT org_name, sector FROM users WHERE id = $1",
                user_id,
            )

            # Org memory
            if user_row and user_row["org_name"]:
                context["org_memory"] = await get_all_memories(user_row["org_name"])
            else:
                context["org_memory"] = {}

            # Recent activity summary
            activity_row = await conn.fetchrow(
                """
                SELECT COUNT(*) as total_sessions,
                       COUNT(DISTINCT s.id) FILTER (WHERE s.created_at > now() - interval '7 days') as recent_sessions
                FROM sessions s
                WHERE s.user_id = $1
                """,
                user_id,
            )
            msg_count = await conn.fetchval(
                """
                SELECT COUNT(*) FROM messages m
                JOIN sessions s ON s.id = m.session_id
                WHERE s.user_id = $1
                """,
                user_id,
            )
            context["recent_activity"] = {
                "total_sessions": activity_row["total_sessions"] if activity_row else 0,
                "recent_sessions_7d": activity_row["recent_sessions"] if activity_row else 0,
                "total_messages": msg_count or 0,
            }

    except Exception as e:
        logger.error("Failed to get user context for %s: %s", user_id, e)
        context.setdefault("preferences", _default_preferences())
        context.setdefault("org_memory", {})
        context.setdefault("recent_activity", {})

    return context


def _default_preferences() -> dict[str, Any]:
    """Return default user preferences."""
    return {
        "theme": "system",
        "language": "en",
        "default_view": "chat",
        "custom_instructions": "",
        "extra": {},
    }
