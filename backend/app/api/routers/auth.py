from fastapi import APIRouter, status

from app.api.deps import AuthServiceDep, AuthUoW
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshRequest, TokenPair
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: UserCreate,
    uow: AuthUoW,
    auth_service: AuthServiceDep,
) -> UserRead:
    user = await auth_service.register(
        uow,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(
    body: LoginRequest,
    uow: AuthUoW,
    auth_service: AuthServiceDep,
) -> TokenPair:
    _, access_token, refresh_token = await auth_service.login(
        uow, email=body.email, password=body.password
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    body: RefreshRequest,
    uow: AuthUoW,
    auth_service: AuthServiceDep,
) -> TokenPair:
    _, access_token, refresh_token = await auth_service.refresh(
        uow, raw_refresh_token=body.refresh_token
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    body: LogoutRequest,
    uow: AuthUoW,
    auth_service: AuthServiceDep,
) -> None:
    await auth_service.logout(uow, raw_refresh_token=body.refresh_token)
