from uuid import UUID

from app.core.uow import AbstractUnitOfWork
from app.models.audit import AuditLog
from app.services.rbac import require_org_role


class AuditService:
    """
    Read-side access to append-only audit_logs.

    Any org member (viewer+) can list; writes happen inside domain services
    (e.g. SecretService reveal).
    """

    async def list_for_organization(
        self,
        uow: AbstractUnitOfWork,
        organization_id: UUID | str,
        *,
        actor_user_id: UUID | str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditLog]:
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        return await uow.audit_logs.list_by_organization(
            organization_id, limit=limit, offset=offset
        )


__all__ = ["AuditService"]
