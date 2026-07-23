from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.uow import AbstractUnitOfWork
from app.models.organization import Membership
from app.services.rbac import (
    InsufficientRoleError,
    MembershipRequiredError,
    require_org_role,
)

INVITABLE_ROLES = frozenset({"admin", "member", "viewer"})


class MembershipNotFoundError(Exception):
    pass


class MembershipAlreadyExistsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


class LastOwnerError(Exception):
    pass


class InvalidMembershipRoleError(Exception):
    pass


class MembershipService:
    """
    Org membership management with application-layer RBAC.

    Viewer is read-only. Invite/role changes require admin+. Promoting to or
    modifying owners requires the actor to be an owner. The last owner cannot
    be demoted or removed.
    """

    async def list(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        actor_user_id: UUID | str,
    ) -> list[Membership]:
        # Any member can list peers (RLS also requires membership + org context).
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        return await uow.memberships.list_by_organization(organization_id)

    async def invite(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        email: str,
        role: str,
        actor_user_id: UUID | str,
    ) -> Membership:
        if role not in INVITABLE_ROLES:
            raise InvalidMembershipRoleError(
                "Cannot invite with role 'owner'; promote an existing member instead."
            )

        actor = await require_org_role(uow, organization_id, actor_user_id, "admin")
        if role == "admin" and actor.role != "owner":
            raise InsufficientRoleError("Only owners can invite admins.")

        user = await uow.users.get_by_email(email)
        if user is None:
            raise UserNotFoundError(f"No user found with email '{email}'.")

        existing = await uow.memberships.get_by_user_and_org(user.id, organization_id)
        if existing is not None:
            raise MembershipAlreadyExistsError("User is already a member of this organization.")

        membership = Membership(
            user_id=user.id,
            organization_id=organization_id,
            role=role,
            invited_by=actor_user_id,
        )
        uow.memberships.add(membership)
        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise MembershipAlreadyExistsError(
                "User is already a member of this organization."
            ) from exc
        return membership

    async def update_role(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        membership_id: UUID | str,
        *,
        new_role: str,
        actor_user_id: UUID | str,
    ) -> Membership:
        if new_role not in {"owner", "admin", "member", "viewer"}:
            raise InvalidMembershipRoleError(f"Invalid role '{new_role}'.")

        actor = await require_org_role(uow, organization_id, actor_user_id, "admin")
        membership = await uow.memberships.get(membership_id)
        if (
            membership is None
            or str(membership.organization_id) != str(organization_id)
        ):
            raise MembershipNotFoundError("Membership not found.")

        if membership.role == new_role:
            return membership

        # Only owners may grant/revoke the owner role or change an owner's role.
        if new_role == "owner" or membership.role == "owner":
            if actor.role != "owner":
                raise InsufficientRoleError("Only owners can change owner roles.")

        if membership.role == "owner" and new_role != "owner":
            owners = await uow.memberships.count_owners(organization_id)
            if owners <= 1:
                raise LastOwnerError("Cannot demote the last owner of the organization.")

        if new_role == "admin" and actor.role not in {"owner"}:
            # Admins may change member/viewer; promoting to admin is owner-only.
            raise InsufficientRoleError("Only owners can promote members to admin.")

        membership.role = new_role
        await uow.commit()
        return membership

    async def remove(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        membership_id: UUID | str,
        *,
        actor_user_id: UUID | str,
    ) -> None:
        actor = await require_org_role(uow, organization_id, actor_user_id, "admin")
        membership = await uow.memberships.get(membership_id)
        if (
            membership is None
            or str(membership.organization_id) != str(organization_id)
        ):
            raise MembershipNotFoundError("Membership not found.")

        if membership.role == "owner":
            if actor.role != "owner":
                raise InsufficientRoleError("Only owners can remove an owner.")
            owners = await uow.memberships.count_owners(organization_id)
            if owners <= 1:
                raise LastOwnerError("Cannot remove the last owner of the organization.")

        await uow.memberships.delete(membership.id)
        await uow.commit()


__all__ = [
    "MembershipService",
    "MembershipNotFoundError",
    "MembershipAlreadyExistsError",
    "UserNotFoundError",
    "LastOwnerError",
    "InvalidMembershipRoleError",
    "InsufficientRoleError",
    "MembershipRequiredError",
]
