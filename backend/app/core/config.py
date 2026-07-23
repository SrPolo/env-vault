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

    # Runtime DB role (FastAPI). Must NOT be a superuser / BYPASSRLS role —
    # otherwise FORCE ROW LEVEL SECURITY is ineffective.
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "envvault_app"
    POSTGRES_PASSWORD: str = "envvault_app_password"
    POSTGRES_DB: str = "envvault_dev"
    POSTGRES_PORT: int = 5432

    # Migration / ops role (Alembic). Local docker-compose uses the cluster
    # superuser (envvault_user). Staging/prod: envvault_migrate (schema owner,
    # no SUPERUSER/BYPASSRLS/CREATEROLE) — see scripts/provision_migration_role.sh.
    MIGRATION_POSTGRES_USER: str = "envvault_user"
    MIGRATION_POSTGRES_PASSWORD: str = "envvault_secure_password"

    def _build_db_uri(self, username: str, password: str) -> PostgresDsn:
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
        return self._build_db_uri(self.POSTGRES_USER, self.POSTGRES_PASSWORD)

    @computed_field
    @property
    def SQLALCHEMY_MIGRATION_URI(self) -> PostgresDsn:
        return self._build_db_uri(
            self.MIGRATION_POSTGRES_USER,
            self.MIGRATION_POSTGRES_PASSWORD,
        )


settings = Settings()
