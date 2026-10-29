from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://docworkspace:docworkspace@localhost:5432/docworkspace"
    session_secret: str = "dev-only-insecure-secret-change-me"  # noqa: S105
    session_max_age_seconds: int = 60 * 60 * 12
    cors_origins: list[str] = ["http://localhost:5173"]

    # S3-compatible attachment storage (ADR-005). Unset bucket = attachments unavailable (503).
    storage_endpoint: str | None = None
    storage_bucket: str | None = None
    storage_access_key: str | None = None
    storage_secret_key: str | None = None
    storage_region: str = "auto"
    # Local/CI only (moto, MinIO): create the bucket on first use. Never needed on R2/S3.
    storage_auto_create_bucket: bool = False

    # Render sets RENDER_GIT_COMMIT; exposed by /health/live so deploys can be verified.
    git_commit: str | None = Field(
        default=None, validation_alias=AliasChoices("GIT_COMMIT", "RENDER_GIT_COMMIT")
    )
    log_level: str = "INFO"

    login_rate_limit_per_minute: int = 20
    upload_rate_limit_per_minute: int = 30

    max_upload_bytes: int = 10 * 1024 * 1024
    max_attachments_per_document: int = 10

    @field_validator("database_url")
    @classmethod
    def normalize_driver(cls, value: str) -> str:
        # Render and most hosts hand out postgres:// URLs; SQLAlchemy needs the explicit driver.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.is_production and settings.session_secret.startswith("dev-only"):
        raise RuntimeError("SESSION_SECRET must be set in production")
    return settings
