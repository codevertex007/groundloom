from dataclasses import dataclass
from typing import Any


@dataclass
class GroundloomError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict[str, Any] | None = None


def not_found() -> GroundloomError:
    return GroundloomError("RESOURCE_NOT_FOUND", "The requested resource was not found.", 404)
