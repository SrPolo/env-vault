from pathlib import Path

from pydantic import PostgresDsn, TypeAdapter, computed_field
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
POSTGRES_DSN_ADAPTER = TypeAdapter(PostgresDsn)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "EnvVault Backend"
    API_V1_STR: str = "/api/v1"

    # KMS / Encryption
    ENCRYPTION_MASTER_KEY: str = "change_me_in_production_min_32_bytes_long!"

    # Admin / migrations (schema owner). In local docker-compose this is the
    # cluster superuser — convenience only; staging/prod should use a locked-down
    # migration role without CREATEROLE/BYPASSRLS.
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "envvault_user"
    POSTGRES_PASSWORD: str = "envvault_secure_password"
    POSTGRES_DB: str = "envvault_dev"
    POSTGRES_PORT: int = 5432

    # Restricted runtime role. FastAPI must use this so FORCE RLS is effective
    # (superusers bypass RLS even with FORCE ROW LEVEL SECURITY).
    APP_DB_USER: str = "envvault_app"
    APP_DB_PASSWORD: str = "envvault_app_password"

    def _build_dsn(self, username: str, password: str) -> PostgresDsn:
        return POSTGRES_DSN_ADAPTER.validate_python(
            str(
                MultiHostUrl.build(
                    scheme="postgresql+asyncpg",
                    username=username,
                    password=password,
                    host=self.POSTGRES_SERVER,
                    port=self.POSTGRES_PORT,
                    path=self.POSTGRES_DB,
                )
            )
        )

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        """Runtime DSN: restricted app role (RLS enforced)."""
        return self._build_dsn(self.APP_DB_USER, self.APP_DB_PASSWORD)

    @computed_field
    @property
    def SQLALCHEMY_ADMIN_DATABASE_URI(self) -> PostgresDsn:
        """Admin DSN: schema owner for Alembic / ops."""
        return self._build_dsn(self.POSTGRES_USER, self.POSTGRES_PASSWORD)


settings = Settings()
