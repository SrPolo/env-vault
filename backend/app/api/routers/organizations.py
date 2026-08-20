from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import (
    CurrentUser,
    MembershipServiceDep,
    OrganizationServiceDep,
    OrgUoW,
    UserUoW,
)
from app.schemas.membership import (
    MembershipInvite,
    MembershipRead,
    MembershipUpdateRole,
)
from app.schemas.organization import (
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
)

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: OrganizationCreate,
    current_user: CurrentUser,
    uow: UserUoW,
    organization_service: OrganizationServiceDep,
) -> OrganizationRead:
    org = await organization_service.create(
        uow,
        name=body.name,
        slug=body.slug,
        user_id=current_user.id,
    )
    return OrganizationRead.model_validate(org)


@router.get("", response_model=list[OrganizationRead])
async def list_organizations(
    uow: UserUoW,
    organization_service: OrganizationServiceDep,
) -> list[OrganizationRead]:
    orgs = await organization_service.list_for_user(uow)
    return [OrganizationRead.model_validate(o) for o in orgs]


@router.get("/{org_id}", response_model=OrganizationRead)
async def get_organization(
    org_id: UUID,
    uow: OrgUoW,
    organization_service: OrganizationServiceDep,
) -> OrganizationRead:
    org = await organization_service.get(uow, org_id)
    return OrganizationRead.model_validate(org)


@router.patch("/{org_id}", response_model=OrganizationRead)
async def update_organization(
    org_id: UUID,
    body: OrganizationUpdate,
    current_user: CurrentUser,
    uow: OrgUoW,
    organization_service: OrganizationServiceDep,
) -> OrganizationRead:
    org = await organization_service.update(
        uow,
        org_id,
        actor_user_id=current_user.id,
        name=body.name,
        slug=body.slug,
    )
    return OrganizationRead.model_validate(org)


@router.delete("/{org_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_organization(
    org_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    organization_service: OrganizationServiceDep,
) -> None:
    await organization_service.delete(
        uow, org_id, actor_user_id=current_user.id
    )


@router.get("/{org_id}/memberships", response_model=list[MembershipRead])
async def list_memberships(
    org_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    membership_service: MembershipServiceDep,
) -> list[MembershipRead]:
    memberships = await membership_service.list(
        uow, org_id, actor_user_id=current_user.id
    )
    return [MembershipRead.model_validate(m) for m in memberships]


@router.post(
    "/{org_id}/memberships",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
)
async def invite_member(
    org_id: UUID,
    body: MembershipInvite,
    current_user: CurrentUser,
    uow: OrgUoW,
    membership_service: MembershipServiceDep,
) -> MembershipRead:
    membership = await membership_service.invite(
        uow,
        org_id,
        email=body.email,
        role=body.role.value,
        actor_user_id=current_user.id,
    )
    return MembershipRead.model_validate(membership)


@router.patch(
    "/{org_id}/memberships/{membership_id}",
    response_model=MembershipRead,
)
async def update_membership_role(
    org_id: UUID,
    membership_id: UUID,
    body: MembershipUpdateRole,
    current_user: CurrentUser,
    uow: OrgUoW,
    membership_service: MembershipServiceDep,
) -> MembershipRead:
    membership = await membership_service.update_role(
        uow,
        org_id,
        membership_id,
        new_role=body.role.value,
        actor_user_id=current_user.id,
    )
    return MembershipRead.model_validate(membership)


@router.delete(
    "/{org_id}/memberships/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_member(
    org_id: UUID,
    membership_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    membership_service: MembershipServiceDep,
) -> None:
    await membership_service.remove(
        uow, org_id, membership_id, actor_user_id=current_user.id
    )
