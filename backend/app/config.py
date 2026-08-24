from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROUNDLOOM_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = "sqlite:///./backend/data/groundloom.db"
    checkpoint_backend: str = "local"
    object_store_path: Path = Path("./backend/data/objects")
    object_store_backend: str = "local"
    object_store_bucket: str | None = None
    object_store_endpoint: str | None = None
    object_store_region: str = "us-east-1"
    object_store_access_key: str | None = None
    object_store_secret_key: str | None = None
    public_base_url: str = "http://localhost:8000"
    cors_origins: list[str] | str = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:4173",
        ]
    )
    local_user_id: str = "local-user"
    local_workspace_id: str = "local-workspace"
    local_user_email: str = "author@local.test"
    local_workspace_name: str = "Local Workspace"
    model_provider: str = "local"
    model_name: str = "deterministic-local"
    telemetry_provider: str = "local"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    max_upload_bytes: int = 25_000_000
    agent_max_attempts: int = 3
    agent_retry_backoff_seconds: float = 0.25
    event_retention_days: int = 90
    auth_secret: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def validate_runtime(self) -> None:
        if self.env == "production":
            if self.database_url.startswith("sqlite"):
                raise RuntimeError(
                    "Production requires PostgreSQL; SQLite is only a local/test adapter"
                )
            if self.model_provider == "local":
                raise RuntimeError("Production requires an explicitly configured model provider")
            if self.telemetry_provider == "local":
                raise RuntimeError("Production requires an explicitly configured telemetry provider")
            if self.object_store_backend != "s3":
                raise RuntimeError("Production requires S3-compatible object storage")
            if not self.object_store_bucket:
                raise RuntimeError("Production requires an object storage bucket")
            if self.checkpoint_backend != "postgres":
                raise RuntimeError("Production requires the Postgres checkpoint backend")
            if not self.auth_secret:
                raise RuntimeError("Production requires auth encryption configuration")
            if "*" in self.cors_origins:
                raise RuntimeError("Production cannot use wildcard CORS")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    if settings.object_store_backend == "local":
        settings.object_store_path.mkdir(parents=True, exist_ok=True)
    return settings
