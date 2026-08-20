from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, OrgUoW, ProjectServiceDep
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter(prefix="/orgs/{org_id}/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    org_id: UUID,
    body: ProjectCreate,
    current_user: CurrentUser,
    uow: OrgUoW,
    project_service: ProjectServiceDep,
) -> ProjectRead:
    project = await project_service.create(
        uow,
        org_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
        actor_user_id=current_user.id,
    )
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    org_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    project_service: ProjectServiceDep,
) -> list[ProjectRead]:
    projects = await project_service.list(
        uow, org_id, actor_user_id=current_user.id
    )
    return [ProjectRead.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    org_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    project_service: ProjectServiceDep,
) -> ProjectRead:
    project = await project_service.get(
        uow,
        project_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    org_id: UUID,
    project_id: UUID,
    body: ProjectUpdate,
    current_user: CurrentUser,
    uow: OrgUoW,
    project_service: ProjectServiceDep,
) -> ProjectRead:
    project = await project_service.update(
        uow,
        project_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
        name=body.name,
        slug=body.slug,
        description=body.description,
    )
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    org_id: UUID,
    project_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    project_service: ProjectServiceDep,
) -> None:
    await project_service.delete(
        uow,
        project_id,
        organization_id=org_id,
        actor_user_id=current_user.id,
    )
