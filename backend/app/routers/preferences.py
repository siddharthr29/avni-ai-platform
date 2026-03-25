"""User preferences and personalization endpoints.

Like ChatGPT's "Custom Instructions" and Claude's "Preferences":
- Custom instructions injected into every LLM call
- Theme, language, default view preferences
- Saved prompt templates
- Org memory (auto-learned context)
- Suggested prompts based on role and history
"""

import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app import db
from app.services import personalization
from app.services.org_memory import get_all_memories

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response Models ────────────────────────────────────────────────


class PreferencesUpdate(BaseModel):
    theme: str | None = Field(default=None, description="UI theme: 'light', 'dark', or 'system'")
    language: str | None = Field(default=None, description="Language code: 'en', 'hi', 'mr', etc.")
    default_view: str | None = Field(default=None, description="Default view: 'chat', 'bundle', 'knowledge'")
    extra: dict[str, Any] | None = Field(default=None, description="Additional preference key-value pairs")


class CustomInstructionsUpdate(BaseModel):
    instructions: str = Field(
        max_length=2000,
        description="Custom instructions text (max 2000 chars). Injected into every LLM call.",
    )


class SavedPromptCreate(BaseModel):
    title: str = Field(description="Short title for the prompt template")
    prompt_text: str = Field(description="The full prompt text")
    category: str = Field(default="general", description="Category: 'general', 'bundle', 'rule', 'support', etc.")
    pinned: bool = Field(default=False, description="Whether to pin this prompt to the top")


# ── Helper to get pool ───────────────────────────────────────────────────────


def _get_pool():
    """Get the database pool, returning None if unavailable."""
    try:
        from app.db import _pool
        return _pool
    except Exception:
        return None


# ── User Profile + Preferences ──────────────────────────────────────────────


@router.get("/me")
async def get_current_user(user_id: str = Query(description="Current user ID")) -> dict:
    """Get current user profile, preferences, and org memory.

    Returns the full user profile along with their personalization preferences
    and any auto-learned org memory.
    """
    user = await db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch preferences
    pool = _get_pool()
    preferences = personalization._default_preferences()
    if pool:
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM user_preferences WHERE user_id = $1",
                    user_id,
                )
                if row:
                    preferences = {
                        "theme": row["theme"],
                        "language": row["language"],
                        "default_view": row["default_view"],
                        "custom_instructions": row["custom_instructions"],
                        "extra": row["preferences"] if isinstance(row["preferences"], dict) else json.loads(row["preferences"]),
                    }
        except Exception as e:
            logger.warning("Failed to fetch preferences for user %s: %s", user_id, e)

    # Fetch org memory
    org_memory = {}
    if user.get("org_name"):
        org_memory = await get_all_memories(user["org_name"])

    return {
        "user": user,
        "preferences": preferences,
        "org_memory": org_memory,
    }


@router.put("/me/preferences")
async def update_preferences(
    user_id: str = Query(description="Current user ID"),
    body: PreferencesUpdate = ...,
) -> dict:
    """Update user preferences (theme, language, default_view, etc.)."""
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            # Fetch existing to merge
            existing = await conn.fetchrow(
                "SELECT * FROM user_preferences WHERE user_id = $1",
                user_id,
            )

            theme = body.theme or (existing["theme"] if existing else "system")
            language = body.language or (existing["language"] if existing else "en")
            default_view = body.default_view or (existing["default_view"] if existing else "chat")

            # Merge extra preferences
            existing_extra: dict = {}
            if existing and existing["preferences"]:
                existing_extra = existing["preferences"] if isinstance(existing["preferences"], dict) else json.loads(existing["preferences"])
            if body.extra:
                existing_extra.update(body.extra)

            custom_instructions = existing["custom_instructions"] if existing else ""

            await conn.execute(
                """
                INSERT INTO user_preferences (user_id, theme, language, default_view, custom_instructions, preferences, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    theme = EXCLUDED.theme,
                    language = EXCLUDED.language,
                    default_view = EXCLUDED.default_view,
                    preferences = EXCLUDED.preferences,
                    updated_at = now()
                """,
                user_id, theme, language, default_view, custom_instructions,
                json.dumps(existing_extra),
            )

        return {
            "ok": True,
            "preferences": {
                "theme": theme,
                "language": language,
                "default_view": default_view,
                "extra": existing_extra,
            },
        }
    except Exception as e:
        logger.error("Failed to update preferences for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to update preferences: {e}")


# ── Custom Instructions ──────────────────────────────────────────────────────


@router.get("/me/custom-instructions")
async def get_custom_instructions(
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """Get the user's custom instructions text."""
    pool = _get_pool()
    if not pool:
        return {"instructions": ""}

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT custom_instructions FROM user_preferences WHERE user_id = $1",
                user_id,
            )
            return {"instructions": row["custom_instructions"] if row else ""}
    except Exception as e:
        logger.warning("Failed to fetch custom instructions: %s", e)
        return {"instructions": ""}


@router.put("/me/custom-instructions")
async def set_custom_instructions(
    user_id: str = Query(description="Current user ID"),
    body: CustomInstructionsUpdate = ...,
) -> dict:
    """Set custom instructions (max 2000 chars).

    These instructions are injected into every LLM call, similar to
    ChatGPT's "Custom Instructions" feature.
    """
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_preferences (user_id, custom_instructions, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (user_id) DO UPDATE SET
                    custom_instructions = EXCLUDED.custom_instructions,
                    updated_at = now()
                """,
                user_id, body.instructions,
            )
        return {"ok": True, "instructions": body.instructions}
    except Exception as e:
        logger.error("Failed to set custom instructions: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save custom instructions: {e}")


# ── Saved Prompts ────────────────────────────────────────────────────────────


@router.get("/me/saved-prompts")
async def list_saved_prompts(
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """List saved prompt templates, sorted by pinned first, then most recently used."""
    pool = _get_pool()
    if not pool:
        return {"prompts": []}

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, title, prompt_text, category, pinned, use_count, created_at, updated_at
                FROM saved_prompts
                WHERE user_id = $1
                ORDER BY pinned DESC, updated_at DESC
                """,
                user_id,
            )
            prompts = [
                {
                    "id": row["id"],
                    "title": row["title"],
                    "prompt_text": row["prompt_text"],
                    "category": row["category"],
                    "pinned": row["pinned"],
                    "use_count": row["use_count"],
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
                for row in rows
            ]
        return {"prompts": prompts}
    except Exception as e:
        logger.error("Failed to list saved prompts: %s", e)
        return {"prompts": []}


@router.post("/me/saved-prompts")
async def create_saved_prompt(
    user_id: str = Query(description="Current user ID"),
    body: SavedPromptCreate = ...,
) -> dict:
    """Save a new prompt template."""
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    prompt_id = str(uuid.uuid4())

    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO saved_prompts (id, user_id, title, prompt_text, category, pinned)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                prompt_id, user_id, body.title, body.prompt_text, body.category, body.pinned,
            )
        return {
            "ok": True,
            "prompt": {
                "id": prompt_id,
                "title": body.title,
                "prompt_text": body.prompt_text,
                "category": body.category,
                "pinned": body.pinned,
                "use_count": 0,
            },
        }
    except Exception as e:
        logger.error("Failed to save prompt: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to save prompt: {e}")


@router.delete("/me/saved-prompts/{prompt_id}")
async def delete_saved_prompt(
    prompt_id: str,
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """Delete a saved prompt template."""
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM saved_prompts WHERE id = $1 AND user_id = $2",
                prompt_id, user_id,
            )
            if result == "DELETE 0":
                raise HTTPException(status_code=404, detail="Prompt not found")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete prompt %s: %s", prompt_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to delete prompt: {e}")


@router.post("/me/saved-prompts/{prompt_id}/use")
async def use_saved_prompt(
    prompt_id: str,
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """Increment use_count for a saved prompt (called when user clicks it)."""
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE saved_prompts
                SET use_count = use_count + 1, updated_at = now()
                WHERE id = $1 AND user_id = $2
                RETURNING id, title, prompt_text, use_count
                """,
                prompt_id, user_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Prompt not found")
        return {
            "ok": True,
            "prompt": {
                "id": row["id"],
                "title": row["title"],
                "prompt_text": row["prompt_text"],
                "use_count": row["use_count"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to increment use_count for prompt %s: %s", prompt_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to update prompt: {e}")


# ── Suggested Prompts ────────────────────────────────────────────────────────


@router.get("/me/suggested-prompts")
async def get_suggested_prompts(
    user_id: str = Query(description="Current user ID"),
    role: str | None = Query(default=None, description="User role: 'ngo_user', 'implementor', 'org_admin'"),
) -> dict:
    """Get context-aware suggested prompts based on role and recent activity.

    Returns 4-6 prompt suggestions tailored to the user's role and
    recent chat intents. Pinned saved prompts are also included.
    """
    # Detect recent intents from chat history
    recent_intents: list[str] = []
    pool = _get_pool()
    if pool:
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT m.metadata->>'intent' as intent
                    FROM messages m
                    JOIN sessions s ON s.id = m.session_id
                    WHERE s.user_id = $1
                      AND m.metadata->>'intent' IS NOT NULL
                    ORDER BY m.created_at DESC
                    LIMIT 5
                    """,
                    user_id,
                )
                recent_intents = [row["intent"] for row in rows if row["intent"]]
        except Exception:
            pass

    suggestions = await personalization.get_suggested_prompts(
        user_id=user_id,
        role=role,
        recent_intents=recent_intents,
    )

    return {"suggestions": suggestions}


# ── Chat History Search ──────────────────────────────────────────────────────


@router.get("/me/chat-history/search")
async def search_chat_history(
    user_id: str = Query(description="Current user ID"),
    q: str = Query(description="Search query"),
    limit: int = Query(default=20, ge=1, le=100, description="Max results"),
) -> dict:
    """Search across all user's chat sessions using full-text search.

    Uses PostgreSQL ts_vector for efficient search across message content.
    Returns matching message snippets with session context.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty")

    results = await personalization.search_chat_history(
        user_id=user_id,
        query=q,
        limit=limit,
    )

    return {"results": results, "total": len(results), "query": q}


# ── Chat History Pin & Export ────────────────────────────────────────────────


@router.post("/me/chat-history/{session_id}/pin")
async def pin_chat_session(
    session_id: str,
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """Toggle pin status on a chat session."""
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    try:
        async with pool.acquire() as conn:
            # Verify session belongs to user
            session = await conn.fetchrow(
                "SELECT id, user_id, pinned FROM sessions WHERE id = $1",
                session_id,
            )
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            if session["user_id"] != user_id:
                raise HTTPException(status_code=403, detail="Not your session")

            new_pinned = not session["pinned"]
            await conn.execute(
                "UPDATE sessions SET pinned = $1 WHERE id = $2",
                new_pinned, session_id,
            )
        return {"ok": True, "pinned": new_pinned}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to pin session %s: %s", session_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to pin session: {e}")


@router.post("/me/chat-history/{session_id}/export")
async def export_chat_session(
    session_id: str,
    user_id: str = Query(description="Current user ID"),
) -> dict:
    """Export a chat session as formatted markdown.

    Returns the full conversation in markdown format suitable for
    saving or sharing.
    """
    pool = _get_pool()
    if not pool:
        raise HTTPException(status_code=503, detail="Database not connected")

    # Verify session belongs to user
    try:
        async with pool.acquire() as conn:
            session = await conn.fetchrow(
                "SELECT user_id FROM sessions WHERE id = $1",
                session_id,
            )
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
            if session["user_id"] != user_id:
                raise HTTPException(status_code=403, detail="Not your session")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to verify session: {e}")

    markdown = await personalization.export_chat_as_markdown(session_id)

    return {"markdown": markdown, "session_id": session_id}
