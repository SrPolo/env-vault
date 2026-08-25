import pytest
from fakeredis import FakeAsyncRedis

from app.core.rate_limit import MemoryRateLimiter, NoOpRateLimiter, RedisRateLimiter


@pytest.mark.asyncio
async def test_memory_rate_limiter_allows_then_blocks() -> None:
    limiter = MemoryRateLimiter()
    assert await limiter.hit("k", limit=2, window_seconds=60) is True
    assert await limiter.hit("k", limit=2, window_seconds=60) is True
    assert await limiter.hit("k", limit=2, window_seconds=60) is False


@pytest.mark.asyncio
async def test_memory_rate_limiter_isolates_keys() -> None:
    limiter = MemoryRateLimiter()
    assert await limiter.hit("a", limit=1, window_seconds=60) is True
    assert await limiter.hit("b", limit=1, window_seconds=60) is True
    assert await limiter.hit("a", limit=1, window_seconds=60) is False


@pytest.mark.asyncio
async def test_noop_rate_limiter_never_blocks() -> None:
    limiter = NoOpRateLimiter()
    for _ in range(100):
        assert await limiter.hit("k", limit=1, window_seconds=60) is True


@pytest.mark.asyncio
async def test_redis_rate_limiter_allows_then_blocks() -> None:
    redis = FakeAsyncRedis(decode_responses=True)
    limiter = RedisRateLimiter(redis)
    try:
        assert await limiter.ping() is True
        assert await limiter.hit("auth:1.2.3.4", limit=2, window_seconds=60) is True
        assert await limiter.hit("auth:1.2.3.4", limit=2, window_seconds=60) is True
        assert await limiter.hit("auth:1.2.3.4", limit=2, window_seconds=60) is False
    finally:
        await limiter.aclose()
