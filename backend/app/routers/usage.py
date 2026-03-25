"""Usage tracking endpoints.

Provides aggregate statistics for the Avni AI Platform:
- Orgs connected, bundles generated/uploaded
- Chat message counts, active users
- Estimated time saved (30% reduction target from Concept Note)
- Top user intents
"""

import logging

from fastapi import APIRouter

from app import db

logger = logging.getLogger(__name__)

router = APIRouter()

# Average time (hours) to manually create an Avni bundle without AI
MANUAL_BUNDLE_HOURS = 8.0
# Target reduction from Concept Note
TARGET_REDUCTION = 0.30


@router.get("/usage/stats")
async def get_usage_stats() -> dict:
    """Get aggregate platform usage statistics."""
    if not db.is_connected():
        return _empty_stats()

    pool = db._pool
    async with pool.acquire() as conn:
        user_count = await conn.fetchval("SELECT COUNT(*) FROM users") or 0
        org_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT org_name) FROM users WHERE org_name != ''"
        ) or 0
        message_count = await conn.fetchval("SELECT COUNT(*) FROM messages") or 0
        session_count = await conn.fetchval("SELECT COUNT(*) FROM sessions") or 0

        # Bundle stats from messages metadata
        bundle_generated = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE metadata->>'intent' = 'bundle_create'"
        ) or 0
        bundle_uploaded = await conn.fetchval(
            "SELECT COUNT(*) FROM messages WHERE metadata->>'action' = 'bundle_upload'"
        ) or 0

        # Top intents from message metadata
        intent_rows = await conn.fetch("""
            SELECT metadata->>'intent' as intent, COUNT(*) as cnt
            FROM messages
            WHERE metadata->>'intent' IS NOT NULL
            GROUP BY metadata->>'intent'
            ORDER BY cnt DESC
            LIMIT 10
        """)

        # Feedback stats
        feedback_stats = await db.get_feedback_stats()

    estimated_hours_saved = bundle_generated * MANUAL_BUNDLE_HOURS * TARGET_REDUCTION
    avg_bundle_time = round(MANUAL_BUNDLE_HOURS * (1 - TARGET_REDUCTION) * 60, 1) if bundle_generated > 0 else 0

    return {
        "orgs_connected": org_count,
        "bundles_generated": bundle_generated,
        "bundles_uploaded": bundle_uploaded,
        "chat_messages": message_count,
        "sessions": session_count,
        "avg_bundle_time_minutes": avg_bundle_time,
        "estimated_hours_saved": round(estimated_hours_saved, 1),
        "active_users": user_count,
        "top_intents": [
            {"intent": r["intent"], "count": r["cnt"]}
            for r in intent_rows
        ],
        "feedback": feedback_stats,
    }


def _empty_stats() -> dict:
    return {
        "orgs_connected": 0,
        "bundles_generated": 0,
        "bundles_uploaded": 0,
        "chat_messages": 0,
        "sessions": 0,
        "avg_bundle_time_minutes": 0,
        "estimated_hours_saved": 0,
        "active_users": 0,
        "top_intents": [],
        "feedback": {},
    }
