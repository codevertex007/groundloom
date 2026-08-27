"""Translate provider SDK failures into Groundloom's stable redacted taxonomy."""

from typing import NoReturn

from ...errors import GroundloomError


def raise_provider_error(dependency_name: str, error: Exception) -> NoReturn:
    """Raise a safe product error without exposing SDK messages or response bodies.

    LangChain integrations own transport, authentication, retries, and response
    decoding. Groundloom still owns the public error contract, so this adapter
    classifies only the status metadata exposed by provider SDK exceptions.
    """

    response = getattr(error, "response", None)
    status_code = getattr(error, "status_code", None) or getattr(response, "status_code", None)
    if isinstance(status_code, int) and 400 <= status_code < 500 and status_code != 429:
        raise GroundloomError(
            "PROVIDER_REJECTED",
            f"The {dependency_name} rejected the request.",
            422,
        ) from error
    raise GroundloomError(
        "DEPENDENCY_UNAVAILABLE",
        f"The {dependency_name} is temporarily unavailable.",
        503,
        retryable=True,
    ) from error
