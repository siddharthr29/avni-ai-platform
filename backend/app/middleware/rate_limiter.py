"""Rate limiter middleware: Redis-backed with in-memory fallback."""

import asyncio
import logging
import time
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Paths exempt from rate limiting
RATE_LIMIT_EXEMPT_PATHS = {
    "/health",
    "/api/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/admin/stats",
}


def _is_exempt(path: str) -> bool:
    return path in RATE_LIMIT_EXEMPT_PATHS or path.startswith("/docs") or path.startswith("/redoc")


class RateLimiter:
    """Rate limiter with Redis backend and in-memory fallback.

    Uses a sliding window counter approach. When Redis is configured and
    reachable it stores counters there; otherwise falls back to an in-memory
    dict with periodic TTL cleanup.
    """

    def __init__(self) -> None:
        self._redis = None  # Will be set if Redis connects successfully
        self._use_redis: bool = False
        # In-memory fallback: key -> list of request timestamps
        self._buckets: dict[str, list[float]] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    async def init(self) -> None:
        """Try connecting to Redis. If unavailable, use in-memory."""
        if settings.REDIS_URL:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=3,
                )
                await self._redis.ping()
                self._use_redis = True
                logger.info("Rate limiter: using Redis at %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning("Rate limiter: Redis unavailable (%s), falling back to in-memory", exc)
                self._redis = None
                self._use_redis = False
        else:
            logger.info("Rate limiter: REDIS_URL not set, using in-memory backend")

        # Start periodic cleanup for in-memory mode
        if not self._use_redis:
            self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

    async def close(self) -> None:
        """Shut down cleanly."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        if self._redis:
            await self._redis.aclose()

    async def check_rate_limit(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        """Check if a request is within the rate limit.

        Returns:
            (allowed, remaining): whether the request is allowed and how many
            requests remain in the current window.
        """
        if self._use_redis:
            return await self._check_redis(key, limit, window_seconds)
        return self._check_memory(key, limit, window_seconds)

    # ── Redis backend ────────────────────────────────────────────────────

    async def _check_redis(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        redis_key = f"ratelimit:{key}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(redis_key, 0, window_start)
            pipe.zadd(redis_key, {str(now): now})
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window_seconds)
            results = await pipe.execute()

            count = results[2]  # zcard result
            if count > limit:
                # Remove the entry we just added — request is denied
                await self._redis.zrem(redis_key, str(now))
                return False, 0
            remaining = max(0, limit - count)
            return True, remaining
        except Exception as exc:
            logger.warning("Redis rate-limit error (%s), allowing request", exc)
            return True, limit  # Fail open

    # ── In-memory backend ────────────────────────────────────────────────

    def _check_memory(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        now = time.time()
        window_start = now - window_seconds

        if key not in self._buckets:
            self._buckets[key] = []

        # Trim expired entries
        self._buckets[key] = [t for t in self._buckets[key] if t > window_start]

        if len(self._buckets[key]) >= limit:
            return False, 0

        self._buckets[key].append(now)
        remaining = max(0, limit - len(self._buckets[key]))
        return True, remaining

    # ── Cleanup ──────────────────────────────────────────────────────────

    async def cleanup(self) -> None:
        """Remove expired entries from in-memory buckets."""
        if self._use_redis:
            return  # Redis handles expiry via EXPIRE/ZREMRANGEBYSCORE
        now = time.time()
        expired_keys = []
        for key, timestamps in self._buckets.items():
            self._buckets[key] = [t for t in timestamps if t > now - 60]
            if not self._buckets[key]:
                expired_keys.append(key)
        for key in expired_keys:
            del self._buckets[key]

    async def _periodic_cleanup(self) -> None:
        """Background task that cleans up expired entries every 60 seconds."""
        while True:
            try:
                await asyncio.sleep(60)
                await self.cleanup()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Rate limiter cleanup error: %s", exc)


# Module-level singleton
rate_limiter = RateLimiter()


# ── FastAPI Middleware ────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI middleware that enforces per-client rate limits.

    Rate-limits by user_id (if authenticated, set by SecurityMiddleware) or
    by client IP address. Adds standard rate-limit response headers.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Skip rate limiting for health/status/docs endpoints and OPTIONS
        if request.method == "OPTIONS" or _is_exempt(path):
            return await call_next(request)

        # Determine rate-limit key: prefer user_id (set by SecurityMiddleware),
        # fall back to client IP.
        rate_key = getattr(request.state, "user_id", None)
        if not rate_key:
            rate_key = request.client.host if request.client else "unknown"

        limit = settings.RATE_LIMIT_RPM
        window = 60  # 1 minute

        allowed, remaining = await rate_limiter.check_rate_limit(rate_key, limit, window)
        reset_at = int(time.time()) + window

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again in a minute."},
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_at),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_at)
        return response
