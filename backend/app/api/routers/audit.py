from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import AuditServiceDep, CurrentUser, OrgUoW
from app.schemas.audit import AuditLogRead

router = APIRouter(prefix="/orgs/{org_id}/audit-logs", tags=["audit"])


@router.get("", response_model=list[AuditLogRead])
async def list_audit_logs(
    org_id: UUID,
    current_user: CurrentUser,
    uow: OrgUoW,
    audit_service: AuditServiceDep,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AuditLogRead]:
    entries = await audit_service.list_for_organization(
        uow,
        org_id,
        actor_user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return [AuditLogRead.model_validate(e) for e in entries]
