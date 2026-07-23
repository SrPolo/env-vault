from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.core.uow import AbstractUnitOfWork
from app.models.project import Environment
from app.models.secret import EncryptionKey
from app.services.crypto import CryptoService
from app.services.rbac import InsufficientRoleError, require_org_role


class EnvironmentNotFoundError(Exception):
    pass


class EnvironmentAlreadyExistsError(Exception):
    pass


class ProjectNotFoundError(Exception):
    pass


class EnvironmentService:
    """
    Environment lifecycle. Creating an environment always provisions an active
    EncryptionKey (wrapped DEK) in the same transaction so SecretService can
    encrypt immediately afterwards.
    """

    def __init__(self, crypto_service: CryptoService):
        self.crypto = crypto_service

    async def create(
        self,
        uow: AbstractUnitOfWork,
        project_id: UUID | str,
        *,
        organization_id: UUID | str,
        name: str,
        actor_user_id: UUID | str,
    ) -> Environment:
        await require_org_role(uow, organization_id, actor_user_id, "member")

        project = await uow.projects.get(project_id)
        if project is None or str(project.organization_id) != str(organization_id):
            raise ProjectNotFoundError("Project not found.")

        existing = await uow.environments.get_by_project_and_name(project_id, name)
        if existing is not None:
            raise EnvironmentAlreadyExistsError(
                f"Environment '{name}' already exists in this project."
            )

        environment = Environment(project_id=project_id, name=name)
        uow.environments.add(environment)
        await uow.flush()

        enc_key = EncryptionKey(
            environment_id=environment.id,
            wrapped_dek=self.crypto.create_wrapped_dek(),
            key_version=1,
            algorithm="AES-256-GCM",
            is_active=True,
        )
        uow.encryption_keys.add(enc_key)

        try:
            await uow.commit()
        except IntegrityError as exc:
            await uow.rollback()
            raise EnvironmentAlreadyExistsError(
                f"Environment '{name}' already exists in this project."
            ) from exc
        return environment

    async def list(
        self,
        uow: AbstractUnitOfWork,
        project_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
    ) -> list[Environment]:
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        project = await uow.projects.get(project_id)
        if project is None or str(project.organization_id) != str(organization_id):
            raise ProjectNotFoundError("Project not found.")
        return await uow.environments.get_by_project(project_id)

    async def get(
        self,
        uow: AbstractUnitOfWork,
        environment_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
    ) -> Environment:
        await require_org_role(uow, organization_id, actor_user_id, "viewer")
        environment = await uow.environments.get(environment_id)
        if environment is None:
            raise EnvironmentNotFoundError("Environment not found.")

        project = await uow.projects.get(environment.project_id)
        if project is None or str(project.organization_id) != str(organization_id):
            raise EnvironmentNotFoundError("Environment not found.")
        return environment

    async def delete(
        self,
        uow: AbstractUnitOfWork,
        environment_id: UUID | str,
        *,
        organization_id: UUID | str,
        actor_user_id: UUID | str,
    ) -> None:
        await require_org_role(uow, organization_id, actor_user_id, "member")
        environment = await self.get(
            uow,
            environment_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
        )
        await uow.environments.delete(environment.id)
        await uow.commit()


__all__ = [
    "EnvironmentService",
    "EnvironmentNotFoundError",
    "EnvironmentAlreadyExistsError",
    "ProjectNotFoundError",
    "InsufficientRoleError",
]
