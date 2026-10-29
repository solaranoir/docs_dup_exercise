from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://docworkspace:docworkspace@localhost:5432/docworkspace"
    session_secret: str = "dev-only-insecure-secret-change-me"  # noqa: S105
    session_max_age_seconds: int = 60 * 60 * 12
    cors_origins: list[str] = ["http://localhost:5173"]

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
