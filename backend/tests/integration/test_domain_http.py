from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

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


async def _register_and_login(
    client: AsyncClient, email: str, password: str = "password123"
) -> str:
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Owner"},
    )
    assert reg.status_code == 201, reg.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_orgs_require_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/orgs")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_full_domain_flow_create_reveal_audits(
    client: AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    admin_engine: AsyncEngine,
) -> None:
    token = await _register_and_login(client, "owner-flow@example.com")
    headers = _auth(token)

    org_resp = await client.post(
        "/api/v1/orgs",
        headers=headers,
        json={"name": "Acme Flow", "slug": "acme-flow"},
    )
    assert org_resp.status_code == 201, org_resp.text
    org_id = org_resp.json()["id"]

    listed = await client.get("/api/v1/orgs", headers=headers)
    assert listed.status_code == 200
    assert any(o["id"] == org_id for o in listed.json())

    project_resp = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=headers,
        json={"name": "API", "slug": "api", "description": "main"},
    )
    assert project_resp.status_code == 201, project_resp.text
    project_id = project_resp.json()["id"]

    env_resp = await client.post(
        f"/api/v1/orgs/{org_id}/projects/{project_id}/environments",
        headers=headers,
        json={"name": "development"},
    )
    assert env_resp.status_code == 201, env_resp.text
    environment_id = env_resp.json()["id"]

    secret_resp = await client.post(
        f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets",
        headers=headers,
        json={"key_name": "DATABASE_URL", "value": "postgres://secret"},
    )
    assert secret_resp.status_code == 201, secret_resp.text
    secret = secret_resp.json()
    assert secret["key_name"] == "DATABASE_URL"
    assert "value" not in secret

    listed_secrets = await client.get(
        f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets",
        headers=headers,
    )
    assert listed_secrets.status_code == 200
    assert [s["key_name"] for s in listed_secrets.json()] == ["DATABASE_URL"]

    reveal = await client.post(
        f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets/"
        f"{secret['id']}/reveal",
        headers=headers,
    )
    assert reveal.status_code == 200, reveal.text
    assert reveal.json()["value"] == "postgres://secret"

    # Audit row must exist (read as superuser to avoid RLS noise in assertion).
    async with admin_engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT action, resource_type, metadata->>'key_name' AS key_name "
                "FROM audit_logs WHERE resource_id = :sid"
            ),
            {"sid": secret["id"]},
        )
        row = result.one()
    assert row.action == "reveal"
    assert row.resource_type == "secret"
    assert row.key_name == "DATABASE_URL"


@pytest.mark.asyncio
async def test_viewer_cannot_reveal_secret_via_http(client: AsyncClient) -> None:
    owner_token = await _register_and_login(client, "owner-rbac@example.com")
    viewer_token = await _register_and_login(client, "viewer-rbac@example.com")
    owner_headers = _auth(owner_token)

    org_id = (
        await client.post(
            "/api/v1/orgs",
            headers=owner_headers,
            json={"name": "RBAC Org", "slug": "rbac-org"},
        )
    ).json()["id"]

    invite = await client.post(
        f"/api/v1/orgs/{org_id}/memberships",
        headers=owner_headers,
        json={"email": "viewer-rbac@example.com", "role": "viewer"},
    )
    assert invite.status_code == 201, invite.text

    project_id = (
        await client.post(
            f"/api/v1/orgs/{org_id}/projects",
            headers=owner_headers,
            json={"name": "P", "slug": "p"},
        )
    ).json()["id"]
    environment_id = (
        await client.post(
            f"/api/v1/orgs/{org_id}/projects/{project_id}/environments",
            headers=owner_headers,
            json={"name": "development"},
        )
    ).json()["id"]
    secret_id = (
        await client.post(
            f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets",
            headers=owner_headers,
            json={"key_name": "API_KEY", "value": "shh"},
        )
    ).json()["id"]

    viewer_headers = _auth(viewer_token)
    listed = await client.get(
        f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets",
        headers=viewer_headers,
    )
    assert listed.status_code == 200

    reveal = await client.post(
        f"/api/v1/orgs/{org_id}/environments/{environment_id}/secrets/"
        f"{secret_id}/reveal",
        headers=viewer_headers,
    )
    assert reveal.status_code == 403
