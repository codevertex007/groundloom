"""Redacted observability adapter.

Telemetry is diagnostic state only. The local adapter is deterministic and
keeps bounded in-process records for tests; a production Langfuse adapter must
be explicitly configured and installed.
"""

from dataclasses import dataclass, field
from typing import Any

SENSITIVE_KEYS = {
    "content",
    "text",
    "source_text",
    "prompt",
    "completion",
    "token",
    "api_key",
    "password",
    "secret",
}


def redact(attributes: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in attributes.items():
        if key.lower() in SENSITIVE_KEYS:
            safe[key] = "[REDACTED]"
        elif isinstance(value, dict):
            safe[key] = redact(value)
        else:
            safe[key] = value
    return safe


@dataclass
class LocalTelemetry:
    records: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event: str, attributes: dict[str, Any]) -> None:
        if len(self.records) >= 500:
            self.records.pop(0)
        self.records.append({"event": event, "attributes": redact(attributes)})

    def record_evaluation(self, report: dict[str, Any]) -> None:
        self.emit("evaluation.completed", report)


class LangfuseTelemetry:
    def __init__(self, public_key: str | None, secret_key: str | None, host: str | None):
        if not public_key or not secret_key or not host:
            raise RuntimeError("Langfuse telemetry requires public key, secret key, and host")
        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise RuntimeError("Install the pinned observability extra for Langfuse") from exc
        self.client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=host,
            tracing_enabled=True,
        )
        self.dropped_events = 0
        self.last_error_class: str | None = None

    def emit(self, event: str, attributes: dict[str, Any]) -> None:
        safe = redact(attributes)
        try:
            self.client.create_event(name=event, metadata=safe)
        except Exception as exc:  # telemetry must never break product state
            self.dropped_events += 1
            self.last_error_class = type(exc).__name__

    def flush(self) -> None:
        try:
            self.client.flush()
        except Exception as exc:  # telemetry remains best-effort
            self.dropped_events += 1
            self.last_error_class = type(exc).__name__

    def record_evaluation(self, report: dict[str, Any]) -> None:
        self.emit("evaluation.completed", report)


def record_evaluation(telemetry: Any, report: dict[str, Any]) -> None:
    """Send a redacted evaluation observation through the configured adapter."""
    recorder = getattr(telemetry, "record_evaluation", None)
    if recorder is None:
        telemetry.emit("evaluation.completed", report)
    else:
        recorder(report)


def build_telemetry(provider: str, public_key: str | None = None, secret_key: str | None = None, host: str | None = None):
    if provider == "local":
        return LocalTelemetry()
    if provider == "langfuse":
        return LangfuseTelemetry(public_key, secret_key, host)
    raise RuntimeError(f"Unsupported telemetry provider: {provider}")
