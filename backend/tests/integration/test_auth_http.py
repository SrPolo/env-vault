from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.deps import get_session_factory
from app.main import create_app


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    application = create_app()
    application.dependency_overrides[get_session_factory] = lambda: session_factory
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_ready(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "up"
    assert body["redis"] == "skipped"


@pytest.mark.asyncio
async def test_request_id_header(client: AsyncClient) -> None:
    response = await client.get("/health", headers={"X-Request-ID": "test-req-1"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-req-1"

    generated = await client.get("/health")
    assert generated.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_auth_rate_limit_returns_429(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api.deps import get_rate_limiter, get_session_factory
    from app.core.config import settings
    from app.core.rate_limit import MemoryRateLimiter

    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_REQUESTS", 3)
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_WINDOW_SECONDS", 60)

    application = create_app()
    limiter = MemoryRateLimiter()
    application.dependency_overrides[get_session_factory] = lambda: session_factory
    application.dependency_overrides[get_rate_limiter] = lambda: limiter

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        for i in range(3):
            resp = await ac.post(
                "/api/v1/auth/login",
                json={"email": f"rl-{i}@example.com", "password": "password123"},
            )
            # Invalid credentials still consume the rate-limit budget.
            assert resp.status_code == 401

        blocked = await ac.post(
            "/api/v1/auth/login",
            json={"email": "rl-block@example.com", "password": "password123"},
        )
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After") == "60"

    application.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_me_and_logout_all(client: AsyncClient) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "me-user@example.com",
            "password": "password123",
            "full_name": "Me User",
        },
    )
    assert register.status_code == 201
    user_id = register.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "me-user@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    body = me.json()
    assert body["id"] == user_id
    assert body["email"] == "me-user@example.com"
    assert body["full_name"] == "Me User"
    assert "password" not in body
    assert "password_hash" not in body

    unauth = await client.get("/api/v1/auth/me")
    assert unauth.status_code == 401

    logout_all = await client.post("/api/v1/auth/logout-all", headers=headers)
    assert logout_all.status_code == 204

    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert reuse.status_code == 401


@pytest.mark.asyncio
async def test_register_login_refresh_logout(client: AsyncClient) -> None:
    register = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "http-user@example.com",
            "password": "password123",
            "full_name": "HTTP User",
        },
    )
    assert register.status_code == 201
    body = register.json()
    assert body["email"] == "http-user@example.com"
    assert body["full_name"] == "HTTP User"
    assert "password" not in body
    assert "password_hash" not in body

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "http-user@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    tokens = login.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh.status_code == 200
    new_tokens = refresh.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert logout.status_code == 204

    reuse = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_tokens["refresh_token"]},
    )
    assert reuse.status_code == 401


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wrong-pw@example.com", "password": "password123"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong-pw@example.com", "password": "nope-nope"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient) -> None:
    payload = {"email": "dup-http@example.com", "password": "password123"}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_orgs_list_requires_bearer(client: AsyncClient) -> None:
    response = await client.get("/api/v1/orgs")
    assert response.status_code == 401
