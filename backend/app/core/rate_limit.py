from __future__ import annotations

import time
from typing import Protocol

from redis.asyncio import Redis


class RateLimiter(Protocol):
    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        """
        Record one hit for ``key``.

        Returns True if the request is allowed, False if the limit is exceeded.
        """
        ...

    async def ping(self) -> bool:
        """Health check. Memory backend always returns True."""
        ...

    async def aclose(self) -> None:
        ...


class NoOpRateLimiter:
    """Pass-through when rate limiting is disabled."""

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        return True

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


class MemoryRateLimiter:
    """
    Fixed-window limiter for tests / local without Redis.

    Not process-safe — production must use RedisRateLimiter.
    """

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, float]] = {}

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        count, expires_at = self._windows.get(key, (0, 0.0))
        if now >= expires_at:
            count = 0
            expires_at = now + window_seconds
        count += 1
        self._windows[key] = (count, expires_at)
        return count <= limit

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self._windows.clear()

    def reset(self) -> None:
        self._windows.clear()


class RedisRateLimiter:
    """Fixed-window limiter backed by Redis INCR + EXPIRE."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
        full_key = f"rl:{key}"
        count = await self._redis.incr(full_key)
        if count == 1:
            await self._redis.expire(full_key, window_seconds)
        return int(count) <= limit

    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    async def aclose(self) -> None:
        await self._redis.aclose()


__all__ = [
    "RateLimiter",
    "NoOpRateLimiter",
    "MemoryRateLimiter",
    "RedisRateLimiter",
]
