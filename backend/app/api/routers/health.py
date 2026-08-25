from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import SessionFactoryDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(
    session_factory: SessionFactoryDep,
    response: Response,
) -> dict[str, str]:
    """Readiness probe — verifies Postgres accepts connections."""
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable", "database": "down"}
    return {"status": "ok", "database": "up"}
