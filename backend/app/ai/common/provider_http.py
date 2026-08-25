"""Bounded JSON HTTP helper shared by narrow model-provider adapters."""

from typing import Any

import httpx

from ...errors import GroundloomError


def post_provider_json(
    endpoint: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: float,
    dependency_name: str,
) -> dict[str, Any]:
    """POST JSON without leaking credentials, request bodies, or response bodies."""

    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise GroundloomError(
            "DEPENDENCY_UNAVAILABLE",
            f"The {dependency_name} is temporarily unavailable.",
            503,
            retryable=True,
        ) from exc
    if response.status_code >= 500:
        raise GroundloomError(
            "DEPENDENCY_UNAVAILABLE",
            f"The {dependency_name} is temporarily unavailable.",
            503,
            retryable=True,
        )
    if response.status_code >= 400:
        raise GroundloomError(
            "PROVIDER_REJECTED",
            f"The {dependency_name} rejected the request.",
            422,
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise GroundloomError(
            "PROVIDER_INVALID_RESPONSE",
            f"The {dependency_name} returned invalid JSON.",
            502,
        ) from exc
    if not isinstance(body, dict):
        raise GroundloomError(
            "PROVIDER_INVALID_RESPONSE",
            f"The {dependency_name} returned an invalid response.",
            502,
        )
    return body
