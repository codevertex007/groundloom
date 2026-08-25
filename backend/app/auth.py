"""Trusted-context authentication adapter.

Local development intentionally uses the seeded identity headers. Staging and
production use a signed bearer context token so clients cannot choose a tenant
by changing request headers. A deployment may replace this adapter with an
OIDC/JWT verifier without changing the service boundary.
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .errors import GroundloomError


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_context_token(
    user_id: str, workspace_id: str, secret: str, *, expires_in_seconds: int = 3600
) -> str:
    payload = {
        "sub": user_id,
        "workspace_id": workspace_id,
        "exp": int(time.time()) + max(1, expires_in_seconds),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_context_token(authorization: str | None, secret: str | None) -> tuple[str, str]:
    if not authorization or not authorization.startswith("Bearer ") or not secret:
        raise GroundloomError("UNAUTHENTICATED", "A valid bearer identity is required.", 401)
    token = authorization.removeprefix("Bearer ")
    try:
        encoded, provided_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("invalid signature")
        payload: dict[str, Any] = json.loads(_decode(encoded))
        user_id = str(payload["sub"])
        workspace_id = str(payload["workspace_id"])
        if int(payload["exp"]) < int(time.time()) or not user_id or not workspace_id:
            raise ValueError("expired or incomplete identity")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GroundloomError("UNAUTHENTICATED", "A valid bearer identity is required.", 401) from exc
    return user_id, workspace_id


def issue_download_token(
    user_id: str,
    workspace_id: str,
    artifact_id: str,
    secret: str,
    *,
    expires_in_seconds: int = 300,
) -> str:
    """Issue a short-lived capability for exactly one export artifact."""
    payload = {
        "kind": "artifact-download",
        "sub": user_id,
        "workspace_id": workspace_id,
        "artifact_id": artifact_id,
        "exp": int(time.time()) + max(1, expires_in_seconds),
    }
    encoded = _encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
    return f"{encoded}.{_encode(signature)}"


def verify_download_token(
    token: str | None,
    secret: str | None,
    artifact_id: str,
) -> tuple[str, str]:
    """Validate a download capability without revealing artifact existence."""
    if not token or not secret:
        raise GroundloomError("UNAUTHENTICATED", "A valid download token is required.", 401)
    try:
        encoded, provided_signature = token.split(".", 1)
        expected_signature = _encode(
            hmac.new(secret.encode(), encoded.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("invalid signature")
        payload: dict[str, Any] = json.loads(_decode(encoded))
        user_id = str(payload["sub"])
        workspace_id = str(payload["workspace_id"])
        if (
            payload.get("kind") != "artifact-download"
            or str(payload["artifact_id"]) != artifact_id
            or int(payload["exp"]) < int(time.time())
            or not user_id
            or not workspace_id
        ):
            raise ValueError("expired or incomplete download capability")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise GroundloomError("UNAUTHENTICATED", "A valid download token is required.", 401) from exc
    return user_id, workspace_id
