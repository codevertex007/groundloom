import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

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
    object_store_connect_timeout_seconds: int = 5
    object_store_read_timeout_seconds: int = 30
    object_store_max_attempts: int = 3
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
    export_inline_local: bool | None = None
    agent_inline_local: bool = True
    worker_heartbeat_timeout_seconds: int = 120
    event_retention_days: int = 90
    auth_secret: str | None = None
    auth_mode: str = "local"

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
            if self.export_inline_local is True:
                raise RuntimeError("Production requires exports to run through the durable worker")
            if self.agent_inline_local:
                raise RuntimeError("Production requires agent runs to use the durable worker")
            if not self.auth_secret:
                raise RuntimeError("Production requires auth encryption configuration")
            if len(self.auth_secret) < 32:
                raise RuntimeError("Production auth secret must be at least 32 characters")
            if self.auth_mode != "hmac":
                raise RuntimeError("Production requires a trusted signed identity adapter")
            if "*" in self.cors_origins:
                raise RuntimeError("Production cannot use wildcard CORS")
            public_url = urlparse(self.public_base_url)
            if public_url.scheme != "https" or not public_url.netloc:
                raise RuntimeError("Production requires an HTTPS public base URL")
            if any("localhost" in origin or "127.0.0.1" in origin for origin in self.cors_origins):
                raise RuntimeError("Production CORS cannot include local development origins")
            if self.telemetry_provider == "langfuse" and not all(
                (self.langfuse_public_key, self.langfuse_secret_key, self.langfuse_host)
            ):
                raise RuntimeError("Production Langfuse telemetry requires keys and host")

    def effective_config_fingerprint(self) -> str:
        """Return a stable fingerprint over non-secret effective settings."""
        safe = {
            "env": self.env,
            "database_backend": self.database_url.split(":", 1)[0],
            "checkpoint_backend": self.checkpoint_backend,
            "object_store_backend": self.object_store_backend,
            "object_store_connect_timeout_seconds": self.object_store_connect_timeout_seconds,
            "object_store_max_attempts": self.object_store_max_attempts,
            "object_store_read_timeout_seconds": self.object_store_read_timeout_seconds,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "telemetry_provider": self.telemetry_provider,
            "agent_inline_local": self.agent_inline_local,
            "agent_max_attempts": self.agent_max_attempts,
            "event_retention_days": self.event_retention_days,
        }
        return hashlib.sha256(
            json.dumps(safe, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    if settings.object_store_backend == "local":
        settings.object_store_path.mkdir(parents=True, exist_ok=True)
    return settings
