from fastapi import APIRouter, Request, Response, status
from sqlalchemy import text

from app.api.deps import SessionFactoryDep
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(
    request: Request,
    session_factory: SessionFactoryDep,
    response: Response,
) -> dict[str, str]:
    """Readiness probe — Postgres required; Redis when rate-limit backend is redis."""
    result: dict[str, str] = {"status": "ok"}

    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        result["database"] = "up"
    except Exception:
        result["database"] = "down"
        result["status"] = "unavailable"

    if (
        settings.RATE_LIMIT_ENABLED
        and settings.RATE_LIMIT_BACKEND == "redis"
    ):
        limiter = getattr(request.app.state, "rate_limiter", None)
        try:
            if limiter is None or not await limiter.ping():
                raise RuntimeError("redis unavailable")
            result["redis"] = "up"
        except Exception:
            result["redis"] = "down"
            result["status"] = "unavailable"
    else:
        result["redis"] = "skipped"

    if result["status"] != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
