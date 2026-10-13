"""Inspect job output files, restricted to the directory shared with the dashboard."""
from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import JobState, OutputFile, OutputStatus
from app.services.normalize import ACTIVE_STATES
from app.services.values import as_str


def _split_list(value: Any) -> list[str]:
    text = as_str(value)
    if text is None:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


class OutputInspector:
    def __init__(self, root: Path, preview_bytes: int = 16384) -> None:
        self.root = Path(os.path.realpath(root))
        self.preview_bytes = preview_bytes

    def references(self, ad: Mapping[str, Any]) -> list[tuple[str, str, Path | None]]:
        base = as_str(ad.get("OutputDirectory")) or as_str(ad.get("Iwd"))
        refs: list[tuple[str, str, Path | None]] = [
            ("result", name, self._join(base, name)) for name in _split_list(ad.get("TransferOutput"))
        ]
        for role, attribute in (("stdout", "Out"), ("stderr", "Err")):
            name = as_str(ad.get(attribute))
            if name and name != "/dev/null":
                refs.append((role, name, self._join(base, name)))
        return refs

    @staticmethod
    def _join(base: str | None, name: str) -> Path | None:
        path = Path(name)
        if path.is_absolute():
            return path
        return Path(base) / path if base else None

    def describe(self, ad: Mapping[str, Any], include_preview: bool = False) -> list[OutputFile]:
        return [self._inspect(role, name, path, include_preview) for role, name, path in self.references(ad)]

    def _inspect(self, role: str, name: str, path: Path | None, include_preview: bool) -> OutputFile:
        if path is None:
            return OutputFile(role=role, name=name, path=name, note="Relative path without a working directory")
        resolved = Path(os.path.realpath(path))
        if not resolved.is_relative_to(self.root):
            return OutputFile(
                role=role, name=name, path=str(path), note="Outside the directory shared with the dashboard"
            )
        try:
            info = resolved.stat()
        except FileNotFoundError:
            return OutputFile(role=role, name=name, path=str(path), exists=False)
        except OSError:
            return OutputFile(role=role, name=name, path=str(path), note="File cannot be read")
        if not stat.S_ISREG(info.st_mode):
            return OutputFile(role=role, name=name, path=str(path), note="Not a regular file")
        preview, truncated = (None, False)
        if include_preview:
            preview, truncated = self._preview(resolved, info.st_size)
        return OutputFile(
            role=role,
            name=name,
            path=str(path),
            exists=True,
            size_bytes=info.st_size,
            modified_at=datetime.fromtimestamp(info.st_mtime, tz=timezone.utc),
            preview=preview,
            truncated=truncated,
        )

    def _preview(self, path: Path, size: int) -> tuple[str | None, bool]:
        try:
            with open(path, "rb") as handle:
                truncated = size > self.preview_bytes
                if truncated:
                    handle.seek(size - self.preview_bytes)
                data = handle.read(self.preview_bytes)
        except OSError:
            return None, False
        return data.decode("utf-8", errors="replace"), truncated

    @staticmethod
    def status(state: JobState, files: list[OutputFile]) -> OutputStatus:
        if state in ACTIVE_STATES:
            return OutputStatus.PENDING
        results = [item for item in files if item.role == "result"]
        if not results:
            return OutputStatus.NONE_DECLARED
        if any(item.exists is None for item in results):
            return OutputStatus.UNKNOWN
        present = sum(1 for item in results if item.exists)
        if present == len(results):
            return OutputStatus.AVAILABLE
        return OutputStatus.MISSING if present == 0 else OutputStatus.PARTIAL
