"""Read-only Deep Agents backend for immutable, application-owned skills.

``SkillPackage``/``SkillSource`` used to live in this module too, but they
carry no deepagents dependency of their own — only ``ReadOnlySkillBackend``
does, since it implements deepagents' ``BackendProtocol``. They now live in
``.skills`` and are re-exported here for backward compatibility; import from
``.skills`` (or the package root) directly if you don't need
``ReadOnlySkillBackend`` and want to avoid requiring the optional `agent`
extra just to import this module.
"""

from __future__ import annotations

import fnmatch
from pathlib import PurePosixPath

from deepagents.backends import BackendProtocol
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

from .skills import SkillPackage, SkillSource

__all__ = ["ReadOnlySkillBackend", "SkillPackage", "SkillSource"]

_ROOT = "/skills/project"


class ReadOnlySkillBackend(BackendProtocol):
    """Expose only a bounded `/skills/project/` projection to Deep Agents."""

    def __init__(self, source: SkillSource):
        self.source = source

    def _snapshot(self) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for package in self.source.list_packages():
            for relative, content in package.files().items():
                files[f"{_ROOT}/{package.slug}/{relative}"] = content
        return files

    @staticmethod
    def _safe(path: str) -> str | None:
        normalized = "/" + str(PurePosixPath(path.replace("\\", "/"))).lstrip("/")
        if normalized != _ROOT and not normalized.startswith(f"{_ROOT}/"):
            return None
        if ".." in PurePosixPath(normalized).parts:
            return None
        return normalized.rstrip("/") or "/"

    def ls(self, path: str) -> LsResult:
        safe = self._safe(path)
        if safe is None:
            return LsResult(error="permission_denied")
        files = self._snapshot()
        prefix = f"{safe}/"
        entries: dict[str, FileInfo] = {}
        for file_path, content in files.items():
            if not file_path.startswith(prefix):
                continue
            remainder = file_path[len(prefix) :]
            first = remainder.split("/", 1)[0]
            child = f"{safe}/{first}"
            is_dir = "/" in remainder
            entry: FileInfo = {"path": child, "is_dir": is_dir}
            if not is_dir:
                entry["size"] = len(content)
            entries[child] = entry
        return LsResult(entries=[entries[key] for key in sorted(entries)])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        safe = self._safe(file_path)
        if safe is None:
            return ReadResult(error="permission_denied")
        content = self._snapshot().get(safe)
        if content is None:
            return ReadResult(error="file_not_found")
        if limit <= 0:
            return ReadResult(
                file_data={"content": "", "encoding": "utf-8"}, no_lines_requested=True
            )
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return ReadResult(error="binary_file")
        lines = text.splitlines()
        start = max(0, offset)
        selected = lines[start : start + limit]
        if not selected and lines:
            return ReadResult(file_data={"content": "", "encoding": "utf-8"})
        if not lines:
            return ReadResult(file_data={"content": "", "encoding": "utf-8"})
        end = start + len(selected)
        return ReadResult(
            file_data={"content": "\n".join(selected), "encoding": "utf-8"},
            start_line=start + 1,
            end_line=end,
            total_lines=len(lines),
            next_offset=end if end < len(lines) else None,
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        files = self._snapshot()
        responses: list[FileDownloadResponse] = []
        for path in paths:
            safe = self._safe(path)
            if safe is None:
                responses.append(FileDownloadResponse(path=path, error="permission_denied"))
            elif safe not in files:
                responses.append(FileDownloadResponse(path=path, error="file_not_found"))
            else:
                responses.append(FileDownloadResponse(path=path, content=files[safe]))
        return responses

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        base = self._safe(path or _ROOT)
        if base is None:
            return GlobResult(error="permission_denied")
        prefix = f"{base}/"
        snapshot = self._snapshot()
        matches: list[FileInfo] = [
            {"path": file_path, "is_dir": False, "size": len(snapshot[file_path])}
            for file_path in sorted(snapshot)
            if file_path.startswith(prefix)
            and fnmatch.fnmatch(file_path[len(prefix) :], pattern.lstrip("/"))
        ]
        return GlobResult(matches=matches)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        base = self._safe(path or _ROOT)
        if base is None:
            return GrepResult(error="permission_denied")
        matches: list[GrepMatch] = []
        for file_path, content in sorted(self._snapshot().items()):
            if not file_path.startswith(f"{base}/"):
                continue
            if glob and not fnmatch.fnmatch(PurePosixPath(file_path).name, glob):
                continue
            try:
                lines = content.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for index, line in enumerate(lines, start=1):
                if pattern in line:
                    matches.append({"path": file_path, "line": index, "text": line})
                    if max_count is not None and len(matches) >= max_count:
                        return GrepResult(matches=matches, truncated=True)
        return GrepResult(matches=matches)

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error="permission_denied")

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error="permission_denied")

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error="permission_denied")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]
