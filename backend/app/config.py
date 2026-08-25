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
    worker_database_url: str | None = None
    migration_database_url: str | None = None
    checkpoint_backend: str = "local"
    object_store_path: Path = Path("./backend/data/objects")
    object_store_backend: str = "local"
    object_store_bucket: str | None = None
    object_store_endpoint: str | None = None
    object_store_region: str = "us-east-1"
    object_store_access_key: str | None = None
    object_store_secret_key: str | None = None
    object_store_sse_mode: Literal["none", "AES256", "aws:kms"] = "none"
    object_store_kms_key_id: str | None = None
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
    embedding_provider: str = "local"
    embedding_model: str = "deterministic-hash-v1"
    embedding_dimensions: int = Field(default=32, ge=4, le=4096)
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    retrieval_index_backend: Literal["auto", "local", "pgvector"] = "auto"
    reranker_provider: str = "local"
    reranker_model: str = "deterministic-overlap-v1"
    reranker_api_key: str | None = None
    reranker_base_url: str | None = None
    reranker_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    evaluator_provider: str = "local"
    evaluator_model: str = "deterministic-rubric-v1"
    evaluator_api_key: str | None = None
    evaluator_base_url: str | None = None
    evaluator_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    source_scanner_provider: str = "local"
    source_scanner_base_url: str | None = None
    source_scanner_api_key: str | None = None
    source_scanner_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    ocr_provider: str = "local"
    ocr_base_url: str | None = None
    ocr_api_key: str | None = None
    ocr_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    ocr_max_output_chars: int = Field(default=20_000_000, ge=1_000, le=50_000_000)
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
    outbox_delivery_provider: str = "disabled"
    outbox_delivery_url: str | None = None
    outbox_delivery_token: str | None = None
    outbox_delivery_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    event_retention_days: int = 90
    auth_secret: str | None = None
    auth_mode: str = "local"
    download_token_ttl_seconds: int = Field(default=300, ge=30, le=3600)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def validate_runtime(self) -> None:
        if self.env in {"staging", "production"} and not self.database_url.startswith("sqlite"):
            self._validate_runtime_database_roles()
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
            if self.object_store_sse_mode == "none":
                raise RuntimeError("Production requires server-side object-storage encryption")
            if self.object_store_sse_mode == "aws:kms" and not self.object_store_kms_key_id:
                raise RuntimeError("AWS KMS object-storage encryption requires a key ID")
            if self.checkpoint_backend != "postgres":
                raise RuntimeError("Production requires the Postgres checkpoint backend")
            if self.retrieval_index_backend == "local":
                raise RuntimeError("Production requires the pgvector retrieval index backend")
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
            if self.source_scanner_provider == "local":
                raise RuntimeError("Production requires an explicitly configured source safety scanner")
            if self.source_scanner_provider in {"http", "http-compatible"} and not all(
                (self.source_scanner_base_url, self.source_scanner_api_key)
            ):
                raise RuntimeError(
                    "The configured production source safety scanner requires endpoint and API key"
                )
            if self.ocr_provider == "local":
                raise RuntimeError("Production requires an explicitly configured OCR provider")
            if self.ocr_provider in {"http", "http-compatible"} and not all(
                (self.ocr_base_url, self.ocr_api_key)
            ):
                raise RuntimeError("The configured production OCR provider requires endpoint and API key")

    def _validate_runtime_database_roles(self) -> None:
        if not self.worker_database_url:
            raise RuntimeError("Staging/production requires a separate worker database URL")
        if not self.migration_database_url:
            raise RuntimeError("Staging/production requires a separate migration database URL")
        worker_user = urlparse(self.worker_database_url).username
        migration_user = urlparse(self.migration_database_url).username
        api_user = urlparse(self.database_url).username
        if worker_user != "groundloom_worker":
            raise RuntimeError("The worker database URL must use the groundloom_worker role")
        if migration_user != "groundloom_migrator":
            raise RuntimeError(
                "The migration database URL must use the groundloom_migrator role"
            )
        if api_user == "groundloom_worker":
            raise RuntimeError("The API database URL cannot use the worker database role")
        if api_user == "groundloom_migrator":
            raise RuntimeError("The API database URL cannot use the migration database role")

    def effective_config_fingerprint(self) -> str:
        """Return a stable fingerprint over non-secret effective settings."""
        safe = {
            "env": self.env,
            "database_backend": self.database_url.split(":", 1)[0],
            "worker_database_backend": (
                self.worker_database_url.split(":", 1)[0]
                if self.worker_database_url
                else None
            ),
            "migration_database_backend": (
                self.migration_database_url.split(":", 1)[0]
                if self.migration_database_url
                else None
            ),
            "checkpoint_backend": self.checkpoint_backend,
            "object_store_backend": self.object_store_backend,
            "object_store_sse_mode": self.object_store_sse_mode,
            "object_store_kms_key_configured": bool(self.object_store_kms_key_id),
            "object_store_connect_timeout_seconds": self.object_store_connect_timeout_seconds,
            "object_store_max_attempts": self.object_store_max_attempts,
            "object_store_read_timeout_seconds": self.object_store_read_timeout_seconds,
            "model_provider": self.model_provider,
            "model_name": self.model_name,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dimensions": self.embedding_dimensions,
            "embedding_base_url": self.embedding_base_url,
            "retrieval_index_backend": self.retrieval_index_backend,
            "reranker_provider": self.reranker_provider,
            "reranker_model": self.reranker_model,
            "reranker_base_url": self.reranker_base_url,
            "evaluator_provider": self.evaluator_provider,
            "evaluator_model": self.evaluator_model,
            "evaluator_base_url": self.evaluator_base_url,
            "source_scanner_provider": self.source_scanner_provider,
            "source_scanner_base_url": self.source_scanner_base_url,
            "ocr_provider": self.ocr_provider,
            "ocr_base_url": self.ocr_base_url,
            "ocr_timeout_seconds": self.ocr_timeout_seconds,
            "ocr_max_output_chars": self.ocr_max_output_chars,
            "telemetry_provider": self.telemetry_provider,
            "agent_inline_local": self.agent_inline_local,
            "agent_max_attempts": self.agent_max_attempts,
            "event_retention_days": self.event_retention_days,
            "outbox_delivery_provider": self.outbox_delivery_provider,
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
