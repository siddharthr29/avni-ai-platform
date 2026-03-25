"""Admin feedback analytics endpoint."""

import logging
from fastapi import APIRouter, HTTPException, Request

from app import db
from app.routers.admin import _require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/feedback-analytics", tags=["Admin Feedback Analytics"])


@router.get("")
async def get_feedback_analytics(request: Request, days: int = 30):
    """Get aggregated feedback analytics."""
    _require_admin(request)
    if not db._pool:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db._pool.acquire() as conn:
        # Check if feedback table exists
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'feedback')"
        )
        if not exists:
            return {
                "total_feedback": 0,
                "thumbs_up": 0,
                "thumbs_down": 0,
                "corrections": 0,
                "satisfaction_rate": 0.0,
                "top_corrected_topics": [],
                "daily_trend": [],
            }

        total = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE created_at > now() - make_interval(days => $1)", days
        )
        thumbs_up = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE rating = 'up' AND created_at > now() - make_interval(days => $1)", days
        )
        thumbs_down = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE rating = 'down' AND created_at > now() - make_interval(days => $1)", days
        )
        corrections = await conn.fetchval(
            "SELECT COUNT(*) FROM feedback WHERE correction IS NOT NULL AND correction != '' "
            "AND created_at > now() - make_interval(days => $1)", days
        )

        satisfaction_rate = (thumbs_up / total * 100) if total > 0 else 0.0

        # Daily trend
        daily_rows = await conn.fetch(
            "SELECT DATE(created_at) as day, "
            "COUNT(*) as total, "
            "COUNT(*) FILTER (WHERE rating = 'up') as positive, "
            "COUNT(*) FILTER (WHERE rating = 'down') as negative "
            "FROM feedback WHERE created_at > now() - make_interval(days => $1) "
            "GROUP BY DATE(created_at) ORDER BY day DESC LIMIT 30",
            days,
        )
        daily_trend = [
            {"date": str(r["day"]), "total": r["total"], "positive": r["positive"], "negative": r["negative"]}
            for r in daily_rows
        ]

        # Top corrected topics (from message content associated with corrections)
        top_topics_rows = await conn.fetch(
            "SELECT LEFT(COALESCE(f.correction, ''), 100) as topic, COUNT(*) as cnt "
            "FROM feedback f "
            "WHERE f.correction IS NOT NULL AND f.correction != '' "
            "AND f.created_at > now() - make_interval(days => $1) "
            "GROUP BY LEFT(COALESCE(f.correction, ''), 100) "
            "ORDER BY cnt DESC LIMIT 10",
            days,
        )
        top_corrected = [{"topic": r["topic"], "count": r["cnt"]} for r in top_topics_rows]

    return {
        "total_feedback": total or 0,
        "thumbs_up": thumbs_up or 0,
        "thumbs_down": thumbs_down or 0,
        "corrections": corrections or 0,
        "satisfaction_rate": round(satisfaction_rate, 1),
        "top_corrected_topics": top_corrected,
        "daily_trend": daily_trend,
    }
