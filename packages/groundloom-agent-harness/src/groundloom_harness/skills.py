"""Immutable skill package contracts, independent of any agent framework.

Split out of ``skills_backend`` so that consumers who only need the plain
``SkillPackage`` data shape (constructing/listing packages) don't have to
have the optional `agent` extra installed just to import this. Only
``ReadOnlySkillBackend`` (in ``skills_backend``) actually needs deepagents,
since it implements deepagents' own backend protocol.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Protocol


def _relative_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or not path.parts or ".." in path.parts or "." in path.parts:
        raise ValueError(f"Invalid skill resource path: {value}")
    return str(path)


@dataclass(frozen=True)
class SkillPackage:
    """One immutable SKILL.md package and its optional supporting resources."""

    slug: str
    skill_md: str
    resources: dict[str, str | bytes] = field(default_factory=dict)

    def files(self) -> dict[str, bytes]:
        if not self.slug or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in self.slug
        ):
            raise ValueError(f"Invalid skill slug: {self.slug}")
        if not self.skill_md.strip():
            raise ValueError("SKILL.md content cannot be empty")
        files = {"SKILL.md": self.skill_md.encode("utf-8")}
        for raw_path, content in self.resources.items():
            path = _relative_path(raw_path)
            if path == "SKILL.md":
                raise ValueError("Skill resources cannot replace SKILL.md")
            files[path] = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        return files


class SkillSource(Protocol):
    def list_packages(self) -> tuple[SkillPackage, ...]:
        """Return an immutable snapshot already authorized by the application."""
