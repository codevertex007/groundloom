"""Scoped binary storage adapters.

The local adapter is used by development and tests. The S3-compatible adapter
is the production boundary; application code only receives validated keys and
never receives credentials or a general-purpose object-store client.
"""

from pathlib import Path
from typing import Protocol

from .config import Settings
from .errors import GroundloomError


class ObjectStore(Protocol):
    def put_bytes(self, key: str, data: bytes) -> None: ...

    def get_bytes(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def delete_bytes(self, key: str) -> None: ...

    def health(self) -> bool: ...


def _validate_key(key: str) -> str:
    path = Path(key)
    if not key or path.is_absolute() or ".." in path.parts or "\\" in key:
        raise GroundloomError("INVALID_INPUT", "Invalid object key.", 422)
    return key


class LocalObjectStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        target = (self.root / _validate_key(key)).resolve()
        if self.root not in target.parents:
            raise GroundloomError("INVALID_INPUT", "Object key escaped the storage root.", 422)
        return target

    def put_bytes(self, key: str, data: bytes) -> None:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def get_bytes(self, key: str) -> bytes:
        target = self._path(key)
        if not target.exists():
            raise GroundloomError("RESOURCE_NOT_FOUND", "The artifact was not found.", 404)
        return target.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete_bytes(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def health(self) -> bool:
        return self.root.exists()


class S3ObjectStore:
    def __init__(self, settings: Settings):
        if not settings.object_store_bucket:
            raise RuntimeError("S3 object storage requires GROUNDLOOM_OBJECT_STORE_BUCKET")
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("Install the storage extra to use S3-compatible object storage") from exc
        if settings.object_store_connect_timeout_seconds <= 0:
            raise RuntimeError("S3 connect timeout must be positive")
        if settings.object_store_read_timeout_seconds <= 0:
            raise RuntimeError("S3 read timeout must be positive")
        if settings.object_store_max_attempts < 1:
            raise RuntimeError("S3 max attempts must be at least one")
        if settings.object_store_sse_mode == "aws:kms" and not settings.object_store_kms_key_id:
            raise RuntimeError("AWS KMS object storage requires GROUNDLOOM_OBJECT_STORE_KMS_KEY_ID")
        self.bucket = settings.object_store_bucket
        self.sse_mode = settings.object_store_sse_mode
        self.kms_key_id = settings.object_store_kms_key_id
        self.client_config = Config(
            connect_timeout=settings.object_store_connect_timeout_seconds,
            read_timeout=settings.object_store_read_timeout_seconds,
            retries={"mode": "standard", "max_attempts": settings.object_store_max_attempts},
        )
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.object_store_endpoint,
            region_name=settings.object_store_region,
            aws_access_key_id=settings.object_store_access_key,
            aws_secret_access_key=settings.object_store_secret_key,
            config=self.client_config,
        )

    @staticmethod
    def _dependency_error(exc: Exception) -> GroundloomError:
        response = getattr(exc, "response", {}) or {}
        code = response.get("Error", {}).get("Code")
        if code in {"NoSuchKey", "404", "NotFound"}:
            return GroundloomError("RESOURCE_NOT_FOUND", "The artifact was not found.", 404)
        return GroundloomError(
            "DEPENDENCY_UNAVAILABLE",
            "Object storage is temporarily unavailable.",
            503,
            retryable=True,
        )

    def _encryption_options(self) -> dict[str, str]:
        if self.sse_mode == "AES256":
            return {"ServerSideEncryption": "AES256"}
        if self.sse_mode == "aws:kms":
            options = {"ServerSideEncryption": "aws:kms"}
            if self.kms_key_id:
                options["SSEKMSKeyId"] = self.kms_key_id
            return options
        return {}

    def put_bytes(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=_validate_key(key),
                Body=data,
                **self._encryption_options(),
            )
        except Exception as exc:
            raise self._dependency_error(exc) from exc

    def get_bytes(self, key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=_validate_key(key))
            return response["Body"].read()
        except Exception as exc:
            raise self._dependency_error(exc) from exc

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=_validate_key(key))
            return True
        except Exception as exc:
            error = self._dependency_error(exc)
            if error.code == "RESOURCE_NOT_FOUND":
                return False
            raise error from exc

    def delete_bytes(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=_validate_key(key))
        except Exception as exc:
            raise self._dependency_error(exc) from exc

    def health(self) -> bool:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True
        except Exception:
            return False


def build_object_store(settings: Settings) -> ObjectStore:
    if settings.object_store_backend == "local":
        return LocalObjectStore(settings.object_store_path)
    if settings.object_store_backend == "s3":
        return S3ObjectStore(settings)
    raise RuntimeError(f"Unsupported object storage backend: {settings.object_store_backend}")
