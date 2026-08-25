from __future__ import annotations

from redis.asyncio import Redis

from app.core.config import settings


def create_redis_client() -> Redis:
    """Build an async Redis client from settings (not connected until first command)."""
    return Redis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )
