"""Durable, project-scoped execution checkpoint storage.

Checkpoints are execution state, not product content. The local adapter uses the
same workspace-scoped object root as the artifact adapter; a production deploy
can replace this seam with the pinned LangGraph Postgres checkpointer.
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .config import Settings
from .errors import GroundloomError

_SAFE_PART = re.compile(r"^[A-Za-z0-9._-]+$")


def _safe_part(value: str, label: str) -> str:
    if not value or not _SAFE_PART.fullmatch(value):
        raise GroundloomError("INVALID_INPUT", f"Invalid {label} for checkpoint scope.", 422)
    return value


def checkpoint_path(settings: Settings, workspace_id: str, project_id: str, thread_id: str) -> Path:
    workspace = _safe_part(workspace_id, "workspace")
    project = _safe_part(project_id, "project")
    thread = _safe_part(thread_id, "thread")
    return settings.object_store_path / "workspaces" / workspace / "checkpoints" / project / f"{thread}.json"


def save_checkpoint(
    settings: Settings,
    workspace_id: str,
    project_id: str,
    thread_id: str,
    state: dict[str, Any],
) -> None:
    target = checkpoint_path(settings, workspace_id, project_id, thread_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    temporary.replace(target)


def load_checkpoint(
    settings: Settings, workspace_id: str, project_id: str, thread_id: str
) -> dict[str, Any] | None:
    target = checkpoint_path(settings, workspace_id, project_id, thread_id)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


class PostgresCheckpointProvider:
    """Verified LangGraph PostgresSaver boundary for production agents."""

    def __init__(self, database_url: str):
        self.database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    @contextmanager
    def open(self) -> Iterator[Any]:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:
            raise RuntimeError(
                "Install the pinned agent extra to use the Postgres checkpoint provider"
            ) from exc
        with PostgresSaver.from_conn_string(self.database_url) as saver:
            saver.setup()
            yield saver


def build_checkpoint_provider(settings: Settings) -> PostgresCheckpointProvider | None:
    if settings.checkpoint_backend == "local":
        return None
    if settings.checkpoint_backend == "postgres":
        return PostgresCheckpointProvider(settings.database_url)
    raise RuntimeError(f"Unsupported checkpoint backend: {settings.checkpoint_backend}")
