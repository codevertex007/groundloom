"""Bounded source safety scanning adapters.

Source bytes are untrusted. The local adapter performs deterministic checks that
are safe to run in-process; deployments can select an HTTP scanner sidecar with
the same narrow verdict contract. Neither adapter executes source content.
"""

import base64
import json
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

import httpx

from .config import Settings
from .errors import GroundloomError


class SourceScanner(Protocol):
    def scan(self, raw: bytes, extension: str) -> None: ...


def _quarantine() -> GroundloomError:
    return GroundloomError(
        "SOURCE_QUARANTINED",
        "The source was quarantined by upload safety checks.",
        422,
    )


@dataclass(frozen=True)
class LocalSourceScanner:
    """Deterministic safety checks for credential-free development."""

    provider_id: str = "local-safety-v1"

    def scan(self, raw: bytes, extension: str) -> None:
        # EICAR is a standard harmless antivirus test fixture, not executable
        # malware. Detecting it proves the quarantine path without requiring a
        # live scanner or allowing real malicious fixtures into the repository.
        if b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" in raw:
            raise _quarantine()
        lowered = raw.lower()
        if extension == "pdf" and any(
            marker in lowered for marker in (b"/javascript", b"/js", b"/launch", b"/openaction")
        ):
            raise _quarantine()
        if extension == "docx":
            try:
                with zipfile.ZipFile(BytesIO(raw)) as archive:
                    names = archive.namelist()
                    if any(
                        name.casefold().endswith(("vbaproject.bin", "/activecontent.xml"))
                        or "/activex/" in name.casefold()
                        for name in names
                    ):
                        raise _quarantine()
                    relationships = b"".join(
                        archive.read(name)
                        for name in names
                        if name.casefold().endswith(".rels")
                    ).lower()
                    if b"targetmode=\"external\"" in relationships:
                        raise _quarantine()
            except zipfile.BadZipFile:
                # Structural validity belongs to the parser stage so the
                # existing PARSE_FAILED contract remains stable.
                return


@dataclass(frozen=True)
class HttpSourceScanner:
    """Narrow JSON scanner-sidecar adapter.

    The sidecar receives `{extension, size_bytes, content_base64}` and returns
    `{verdict: "clean"|"quarantine"}`. Provider details never cross the
    product error boundary.
    """

    base_url: str
    api_key: str
    timeout_seconds: float = 15.0
    provider_id: str = "http-safety-scanner"

    def scan(self, raw: bytes, extension: str) -> None:
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/scan"):
            endpoint = f"{endpoint}/scan"
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
                "The source safety scanner is temporarily unavailable.",
                503,
                retryable=True,
            ) from exc
        if response.status_code >= 500:
            raise GroundloomError(
                "DEPENDENCY_UNAVAILABLE",
                "The source safety scanner is temporarily unavailable.",
                503,
                retryable=True,
            )
        if response.status_code >= 400:
            raise GroundloomError(
                "PROVIDER_REJECTED",
                "The source safety scanner rejected the request.",
                422,
            )
        try:
            verdict = str(response.json()["verdict"])
        except (AttributeError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The source safety scanner returned an invalid result.",
                502,
            ) from exc
        if verdict == "quarantine":
            raise _quarantine()
        if verdict != "clean":
            raise GroundloomError(
                "PROVIDER_INVALID_RESPONSE",
                "The source safety scanner returned an invalid result.",
                502,
            )


def build_source_scanner(settings: Settings | None = None) -> SourceScanner:
    settings = settings or Settings()
    provider = settings.source_scanner_provider.casefold()
    if provider == "local":
        return LocalSourceScanner()
    if provider in {"http", "http-compatible"}:
        if not settings.source_scanner_base_url or not settings.source_scanner_api_key:
            raise GroundloomError(
                "PROVIDER_MISCONFIGURED",
                "The configured source safety scanner is missing credentials or endpoint.",
                503,
            )
        return HttpSourceScanner(
            base_url=settings.source_scanner_base_url,
            api_key=settings.source_scanner_api_key,
            timeout_seconds=settings.source_scanner_timeout_seconds,
        )
    raise GroundloomError(
        "PROVIDER_MISCONFIGURED",
        "The configured source safety scanner is unsupported.",
        503,
    )
