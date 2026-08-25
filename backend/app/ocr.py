"""Bounded OCR provider boundary for image-only source documents.

OCR is deterministic infrastructure around the primary agent. The local
adapter refuses to claim OCR success; deployments may use a narrow HTTP
sidecar that returns bounded extracted text.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Protocol

import httpx

from .config import Settings
from .errors import GroundloomError


class OCRProvider(Protocol):
    @property
    def provider_id(self) -> str: ...

    def extract(self, raw: bytes, extension: str) -> str:
        """Extract bounded text from an image-only supported document."""


@dataclass(frozen=True)
class LocalOCRProvider:
    """Explicit local failure adapter; it never fabricates OCR output."""

    provider_id: str = "local-ocr-unavailable"

    def extract(self, raw: bytes, extension: str) -> str:
        del raw, extension
        raise GroundloomError(
            "PROVIDER_MISCONFIGURED",
            "OCR is not configured for image-only documents.",
            503,
        )


@dataclass(frozen=True)
class HttpOCRProvider:
    """Narrow OCR sidecar adapter with bounded request and response contracts."""

    base_url: str
    api_key: str
    timeout_seconds: float = 30.0
    max_output_chars: int = 20_000_000
    provider_id: str = "http-ocr"

    def extract(self, raw: bytes, extension: str) -> str:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/ocr"):
            endpoint = f"{endpoint}/ocr"
        try:
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "extension": extension,
                    "size_bytes": len(raw),
                    "content_base64": base64.b64encode(raw).decode("ascii"),
                },
                timeout=self.timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The OCR service is temporarily unavailable.",
                503,
                retryable=True,
            ) from exc
        if response.status_code >= 500:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The OCR service is temporarily unavailable.",
                503,
                retryable=True,
            )
        if response.status_code >= 400:
            raise GroundloomError(
                "PROVIDER_REJECTED",
                "The OCR service rejected the document.",
                422,
            )
        try:
            text = response.json()["text"]
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The OCR service returned an invalid result.",
                502,
            ) from exc
        if not isinstance(text, str) or not text.strip() or len(text) > self.max_output_chars:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The OCR service returned invalid or oversized text.",
                502,
            )
        return text


def build_ocr_provider(settings: Settings | None = None) -> OCRProvider:
    settings = settings or Settings()
    provider = settings.ocr_provider.casefold()
    if provider == "local":
        return LocalOCRProvider()
    if provider in {"http", "http-compatible"}:
        if not settings.ocr_base_url or not settings.ocr_api_key:
            raise GroundloomError(
                "PROVIDER_MISCONFIGURED",
                "The configured OCR provider is missing credentials or endpoint.",
                503,
            )
        return HttpOCRProvider(
            base_url=settings.ocr_base_url,
            api_key=settings.ocr_api_key,
            timeout_seconds=settings.ocr_timeout_seconds,
            max_output_chars=settings.ocr_max_output_chars,
        )
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured OCR provider is unsupported.",
        503,
    )
