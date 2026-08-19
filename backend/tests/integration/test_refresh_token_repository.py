from datetime import datetime, timedelta, timezone

import pytest

from app.models.user import RefreshToken
from tests.factories import TenantFixture


def _future(minutes: int = 30) -> datetime:
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


@pytest.mark.asyncio
async def test_refresh_token_lookup_and_revocation(
    uow_factory,
    tenant: TenantFixture,
) -> None:
    async with uow_factory() as uow:
        uow.refresh_tokens.add(
            RefreshToken(
                user_id=tenant.user_id,
                token_hash="hash-a",
                expires_at=_future(),
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        found = await uow.refresh_tokens.get_by_token_hash("hash-a")
        assert found is not None
        assert found.revoked_at is None
        assert await uow.refresh_tokens.get_by_token_hash("missing") is None

        await uow.refresh_tokens.revoke(found.id)
        await uow.commit()

    async with uow_factory() as uow:
        revoked = await uow.refresh_tokens.get_by_token_hash("hash-a")
        assert revoked is not None
        assert revoked.revoked_at is not None
        assert await uow.refresh_tokens.list_active_for_user(tenant.user_id) == []


@pytest.mark.asyncio
async def test_expired_tokens_are_not_listed_as_active(
    uow_factory,
    tenant: TenantFixture,
) -> None:
    async with uow_factory() as uow:
        uow.refresh_tokens.add(
            RefreshToken(
                user_id=tenant.user_id,
                token_hash="hash-live",
                expires_at=_future(),
            )
        )
        uow.refresh_tokens.add(
            RefreshToken(
                user_id=tenant.user_id,
                token_hash="hash-expired",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        await uow.commit()

    async with uow_factory() as uow:
        active = await uow.refresh_tokens.list_active_for_user(tenant.user_id)
        assert [t.token_hash for t in active] == ["hash-live"]


@pytest.mark.asyncio
async def test_revoke_all_for_user_kills_every_active_token(
    uow_factory,
    tenant: TenantFixture,
) -> None:
    """Backs the reuse-detection strategy: a replayed token logs out all devices."""
    async with uow_factory() as uow:
        for suffix in ("laptop", "phone", "ci"):
            uow.refresh_tokens.add(
                RefreshToken(
                    user_id=tenant.user_id,
                    token_hash=f"hash-{suffix}",
                    expires_at=_future(),
                )
            )
        await uow.commit()

    async with uow_factory() as uow:
        assert len(await uow.refresh_tokens.list_active_for_user(tenant.user_id)) == 3
        await uow.refresh_tokens.revoke_all_for_user(tenant.user_id)
        await uow.commit()

    async with uow_factory() as uow:
        assert await uow.refresh_tokens.list_active_for_user(tenant.user_id) == []
