from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://docworkspace:docworkspace@localhost:5432/docworkspace"
    session_secret: str = "dev-only-insecure-secret-change-me"  # noqa: S105
    # Server-side sessions (ADR-009): idle timeout, absolute lifetime, and how often
    # last_seen_at is refreshed (avoids a write on every request).
    session_idle_seconds: int = 60 * 60 * 24 * 7
    session_absolute_seconds: int = 60 * 60 * 24 * 30
    session_touch_seconds: int = 60 * 5
    # Browser origins allowed for CORS *and* for unsafe methods (CSRF origin check).
    cors_origins: list[str] = ["http://localhost:5173"]
    # Seeded Alice/Bob/Charlie switcher (ADR-004). Local development and tests only;
    # never honoured in production.
    enable_demo_auth: bool = False

    # OAuth sign-in (ADR-009). A provider is offered only when both values are set.
    github_client_id: str | None = None
    github_client_secret: str | None = None
    google_client_id: str | None = None
    google_client_secret: str | None = None
    # Public web origin used to build OAuth callback URLs. Defaults to the first CORS origin,
    # which in production is the web origin that rewrites /api to this service.
    public_base_url: str | None = None

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

    @property
    def demo_auth_enabled(self) -> bool:
        return self.enable_demo_auth and not self.is_production

    @property
    def session_cookie_name(self) -> str:
        # __Host- requires Secure + Path=/ and no Domain, so sibling subdomains cannot set or
        # shadow it. Browsers reject Secure cookies over plain http, so dev uses a plain name.
        return "__Host-sd_session" if self.is_production else "sd_session"

    @property
    def app_origin(self) -> str:
        return (self.public_base_url or self.cors_origins[0]).rstrip("/")

    @property
    def oauth_providers(self) -> list[str]:
        configured = {
            "github": self.github_client_id and self.github_client_secret,
            "google": self.google_client_id and self.google_client_secret,
        }
        return [name for name, ok in configured.items() if ok]

    @property
    def trusted_origins(self) -> frozenset[str]:
        return frozenset(o.rstrip("/") for o in self.cors_origins)

    def check_production(self) -> None:
        if not self.is_production:
            return
        if self.session_secret.startswith("dev-only"):
            raise RuntimeError("SESSION_SECRET must be set in production")
        if self.enable_demo_auth:
            raise RuntimeError("ENABLE_DEMO_AUTH must not be set in production")
        if not self.cors_origins or any(not o.startswith("https://") for o in self.cors_origins):
            raise RuntimeError("CORS_ORIGINS must list the https:// web origin in production")
        if not self.app_origin.startswith("https://"):
            raise RuntimeError("PUBLIC_BASE_URL must be https:// in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check_production()
    return settings
