from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.exception_handlers import register_exception_handlers
from app.api.routers import (
    audit,
    auth,
    environments,
    health,
    organizations,
    projects,
    secrets,
)
from app.core.config import settings


def create_app() -> FastAPI:
    application = FastAPI(title=settings.PROJECT_NAME)
    register_exception_handlers(application)

    if settings.CORS_ORIGINS:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(health.router)
    application.include_router(auth.router, prefix=settings.API_V1_STR)
    application.include_router(organizations.router, prefix=settings.API_V1_STR)
    application.include_router(audit.router, prefix=settings.API_V1_STR)
    application.include_router(projects.router, prefix=settings.API_V1_STR)
    application.include_router(environments.router, prefix=settings.API_V1_STR)
    application.include_router(secrets.router, prefix=settings.API_V1_STR)
    return application


app = create_app()
