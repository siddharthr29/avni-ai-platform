"""Redis-backed cache for temporary data (parsed SRS, bundle review state).

Falls back to in-memory dict when Redis is unavailable.
All values are JSON-serialized. TTL defaults to 1 hour.
"""

import json
import logging
import time
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TTL = 3600  # 1 hour


class Cache:
    """Async cache with Redis backend and in-memory fallback."""

    def __init__(self) -> None:
        self._redis = None
        self._use_redis = False
        # In-memory fallback: key -> (value_json, expire_at)
        self._memory: dict[str, tuple[str, float]] = {}

    async def init(self) -> None:
        """Connect to Redis if available."""
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
                logger.info("Cache: using Redis at %s", settings.REDIS_URL)
            except Exception as exc:
                logger.warning("Cache: Redis unavailable (%s), using in-memory", exc)
                self._redis = None
                self._use_redis = False
        else:
            logger.info("Cache: REDIS_URL not set, using in-memory")

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def set(self, key: str, value: Any, ttl: int = DEFAULT_TTL) -> None:
        """Store a value. Value is JSON-serialized."""
        data = json.dumps(value, default=str)
        if self._use_redis:
            try:
                await self._redis.setex(f"cache:{key}", ttl, data)
                return
            except Exception as exc:
                logger.warning("Cache Redis set failed: %s", exc)
        # In-memory fallback
        self._memory[key] = (data, time.time() + ttl)

    async def get(self, key: str) -> Any | None:
        """Retrieve a value. Returns None if not found or expired."""
        if self._use_redis:
            try:
                data = await self._redis.get(f"cache:{key}")
                if data:
                    return json.loads(data)
                return None
            except Exception as exc:
                logger.warning("Cache Redis get failed: %s", exc)
        # In-memory fallback
        entry = self._memory.get(key)
        if entry:
            data, expire_at = entry
            if time.time() < expire_at:
                return json.loads(data)
            del self._memory[key]
        return None

    async def delete(self, key: str) -> None:
        """Remove a key."""
        if self._use_redis:
            try:
                await self._redis.delete(f"cache:{key}")
            except Exception:
                pass
        self._memory.pop(key, None)

    async def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        return (await self.get(key)) is not None


# Module-level singleton
cache = Cache()


# ── Convenience functions for SRS/Bundle caching ──

async def cache_parsed_srs(bundle_id: str, srs_data: Any, ttl: int = 3600) -> None:
    """Cache parsed SRS data for review wizard. TTL = 1 hour."""
    # Convert Pydantic model to dict
    if hasattr(srs_data, 'model_dump'):
        data = srs_data.model_dump()
    elif hasattr(srs_data, 'dict'):
        data = srs_data.dict()
    else:
        data = srs_data
    await cache.set(f"srs:{bundle_id}", data, ttl)
    logger.info("Cached SRS data for bundle %s (TTL=%ds)", bundle_id, ttl)


async def get_cached_srs(bundle_id: str) -> dict | None:
    """Retrieve cached SRS data for review wizard."""
    return await cache.get(f"srs:{bundle_id}")


async def cache_bundle_review(bundle_id: str, review_data: dict, ttl: int = 3600) -> None:
    """Cache bundle review state (user's fixes applied so far)."""
    await cache.set(f"review:{bundle_id}", review_data, ttl)


async def get_bundle_review(bundle_id: str) -> dict | None:
    """Retrieve bundle review state."""
    return await cache.get(f"review:{bundle_id}")


async def cache_bundle_fixes(bundle_id: str, fixes: list[dict], ttl: int = 3600) -> None:
    """Cache user-submitted fixes for a bundle."""
    await cache.set(f"fixes:{bundle_id}", fixes, ttl)


async def get_bundle_fixes(bundle_id: str) -> list[dict] | None:
    """Retrieve cached fixes."""
    return await cache.get(f"fixes:{bundle_id}")
