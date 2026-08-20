from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.auth import (
    EmailAlreadyRegisteredError,
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from app.services.environment import (
    EnvironmentAlreadyExistsError,
    EnvironmentNotFoundError,
)
from app.services.membership import (
    InvalidMembershipRoleError,
    LastOwnerError,
    MembershipAlreadyExistsError,
    MembershipNotFoundError,
    UserNotFoundError,
)
from app.services.organization import (
    OrganizationAlreadyExistsError,
    OrganizationNotFoundError,
)
from app.services.project import ProjectAlreadyExistsError, ProjectNotFoundError
from app.services.rbac import InsufficientRoleError, MembershipRequiredError
from app.services.secret import (
    EncryptionKeyNotFoundError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
)

# Domain exceptions → HTTP status. Detail is the exception message.
_STATUS_MAP: dict[type[Exception], int] = {
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    InvalidRefreshTokenError: status.HTTP_401_UNAUTHORIZED,
    InactiveUserError: status.HTTP_403_FORBIDDEN,
    InsufficientRoleError: status.HTTP_403_FORBIDDEN,
    MembershipRequiredError: status.HTTP_403_FORBIDDEN,
    LastOwnerError: status.HTTP_403_FORBIDDEN,
    EmailAlreadyRegisteredError: status.HTTP_409_CONFLICT,
    OrganizationAlreadyExistsError: status.HTTP_409_CONFLICT,
    MembershipAlreadyExistsError: status.HTTP_409_CONFLICT,
    ProjectAlreadyExistsError: status.HTTP_409_CONFLICT,
    EnvironmentAlreadyExistsError: status.HTTP_409_CONFLICT,
    SecretAlreadyExistsError: status.HTTP_409_CONFLICT,
    OrganizationNotFoundError: status.HTTP_404_NOT_FOUND,
    MembershipNotFoundError: status.HTTP_404_NOT_FOUND,
    UserNotFoundError: status.HTTP_404_NOT_FOUND,
    ProjectNotFoundError: status.HTTP_404_NOT_FOUND,
    EnvironmentNotFoundError: status.HTTP_404_NOT_FOUND,
    SecretNotFoundError: status.HTTP_404_NOT_FOUND,
    EncryptionKeyNotFoundError: status.HTTP_404_NOT_FOUND,
    InvalidMembershipRoleError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


async def domain_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    code = _STATUS_MAP.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    return JSONResponse(status_code=code, content={"detail": str(exc)})


def register_exception_handlers(app: FastAPI) -> None:
    for exc_type in _STATUS_MAP:
        app.add_exception_handler(exc_type, domain_exception_handler)
