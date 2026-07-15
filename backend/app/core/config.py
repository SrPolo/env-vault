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
    
    # Configuración DB
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_USER: str = "envvault_user"
    POSTGRES_PASSWORD: str = "envvault_secure_password"
    POSTGRES_DB: str = "envvault_dev"
    POSTGRES_PORT: int = 5432

    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return POSTGRES_DSN_ADAPTER.validate_python(
            str(
                MultiHostUrl.build(
                    scheme="postgresql+asyncpg",
                    username=self.POSTGRES_USER,
                    password=self.POSTGRES_PASSWORD,
                    host=self.POSTGRES_SERVER,
                    port=self.POSTGRES_PORT,
                    path=self.POSTGRES_DB,
                )
            )
        )

settings = Settings()