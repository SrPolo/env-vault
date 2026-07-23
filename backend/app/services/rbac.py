from uuid import UUID

from app.core.uow import AbstractUnitOfWork
from app.models.organization import Membership

ROLE_RANK: dict[str, int] = {
    "viewer": 0,
    "member": 1,
    "admin": 2,
    "owner": 3,
}

# Roles that may mutate org resources (projects, environments, secrets).
WRITE_ROLES = frozenset({"owner", "admin", "member"})
ADMIN_ROLES = frozenset({"owner", "admin"})


class InsufficientRoleError(Exception):
    pass


class MembershipRequiredError(Exception):
    pass


async def get_actor_membership(
    uow: AbstractUnitOfWork,
    organization_id: UUID | str,
    actor_user_id: UUID | str,
) -> Membership:
    membership = await uow.memberships.get_by_user_and_org(actor_user_id, organization_id)
    if membership is None:
        raise MembershipRequiredError("Actor is not a member of this organization.")
    return membership


def require_min_role(membership: Membership, minimum: str) -> None:
    actor_rank = ROLE_RANK.get(membership.role, -1)
    required_rank = ROLE_RANK[minimum]
    if actor_rank < required_rank:
        raise InsufficientRoleError(
            f"Role '{membership.role}' is insufficient; requires '{minimum}' or higher."
        )


async def require_org_role(
    uow: AbstractUnitOfWork,
    organization_id: UUID | str,
    actor_user_id: UUID | str,
    minimum: str,
) -> Membership:
    membership = await get_actor_membership(uow, organization_id, actor_user_id)
    require_min_role(membership, minimum)
    return membership
