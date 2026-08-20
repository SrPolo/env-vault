from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OrgUoW, SecretServiceDep
from app.schemas.secret import SecretCreate, SecretRead, SecretReveal, SecretUpdate

router = APIRouter(
    prefix="/orgs/{org_id}/environments/{environment_id}/secrets",
    tags=["secrets"],
)


@router.get("", response_model=list[SecretRead])
async def list_secrets(
    org_id: UUID,
    environment_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    secret_service: SecretServiceDep,
) -> list[SecretRead]:
    secrets = await secret_service.list_secrets(
        uow,
        environment_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
    return [SecretRead.model_validate(s) for s in secrets]


@router.post("", response_model=SecretRead, status_code=status.HTTP_201_CREATED)
async def create_secret(
    org_id: UUID,
    environment_id: UUID,
    body: SecretCreate,
    current_user: CurrentUser,
    uow: OrgUoW,
    secret_service: SecretServiceDep,
) -> SecretRead:
    secret = await secret_service.create_secret(
        uow,
        environment_id,
        organization_id=org_id,
        key_name=body.key_name,
        plain_value=body.value,
        actor_user_id=current_user.id,
    )
    return SecretRead.model_validate(secret)


@router.put("/{secret_id}", response_model=SecretRead)
async def rotate_secret(
    org_id: UUID,
    secret_id: UUID,
    body: SecretUpdate,
    current_user: CurrentUser,
    uow: OrgUoW,
    secret_service: SecretServiceDep,
) -> SecretRead:
    await secret_service.add_new_version(
        uow,
        secret_id,
        organization_id=org_id,
        plain_value=body.value,
        actor_user_id=current_user.id,
    )
    # Reload metadata after rotation (new version pointer).
    secret = await uow.secrets.get(secret_id)
    assert secret is not None
    return SecretRead.model_validate(secret)


@router.post("/{secret_id}/reveal", response_model=SecretReveal)
async def reveal_secret(
    org_id: UUID,
    secret_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    secret_service: SecretServiceDep,
) -> SecretReveal:
    value = await secret_service.get_decrypted_value(
        uow,
        secret_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
    secret = await uow.secrets.get(secret_id)
    assert secret is not None
    return SecretReveal(id=secret.id, key_name=secret.key_name, value=value)


@router.delete("/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_secret(
    org_id: UUID,
    secret_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    secret_service: SecretServiceDep,
) -> None:
    await secret_service.delete_secret(
        uow,
        secret_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
