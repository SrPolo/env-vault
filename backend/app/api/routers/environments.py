from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, EnvironmentServiceDep, OrgUoW
from app.schemas.environment import EnvironmentCreate, EnvironmentRead

router = APIRouter(
    prefix="/orgs/{org_id}/projects/{project_id}/environments",
    tags=["environments"],
)


@router.post("", response_model=EnvironmentRead, status_code=status.HTTP_201_CREATED)
async def create_environment(
    org_id: UUID,
    project_id: UUID,
    body: EnvironmentCreate,
    current_user: CurrentUser,
    uow: OrgUoW,
    environment_service: EnvironmentServiceDep,
) -> EnvironmentRead:
    environment = await environment_service.create(
        uow,
        project_id,
        organization_id=org_id,
        name=body.name,
        actor_user_id=current_user.id,
    )
    return EnvironmentRead.model_validate(environment)


@router.get("", response_model=list[EnvironmentRead])
async def list_environments(
    org_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    environment_service: EnvironmentServiceDep,
) -> list[EnvironmentRead]:
    environments = await environment_service.list(
        uow,
        project_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
    return [EnvironmentRead.model_validate(e) for e in environments]


@router.get("/{environment_id}", response_model=EnvironmentRead)
async def get_environment(
    org_id: UUID,
    environment_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    environment_service: EnvironmentServiceDep,
) -> EnvironmentRead:
    environment = await environment_service.get(
        uow,
        environment_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
    return EnvironmentRead.model_validate(environment)


@router.delete("/{environment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_environment(
    org_id: UUID,
    environment_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    environment_service: EnvironmentServiceDep,
) -> None:
    await environment_service.delete(
        uow,
        environment_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
