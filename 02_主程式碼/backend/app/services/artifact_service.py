"""Safe, atomic creation of downloadable job artifacts."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Iterable


class ArtifactError(ValueError):
    """Raised when an artifact would escape its managed workspace."""


def _within(root: Path, value: str | Path) -> Path:
    root = root.resolve()
    path = Path(value).resolve()
    if not path.is_relative_to(root):
        raise ArtifactError(f"Artifact path is outside the job workspace: {path.name}")
    return path


def create_result_archive(
    workspace: str | Path,
    sources: Iterable[str | Path],
    *,
    filename: str = "results.zip",
) -> Path:
    """Archive workspace-owned files/directories without following symlinks.

    The archive is first written beside its final destination and atomically
    replaced, so a download endpoint never observes a partially-written ZIP.
    """

    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    destination = _within(workspace, workspace / filename)
    if destination.suffix.lower() != ".zip":
        raise ArtifactError("Download artifacts must use the .zip extension.")
    selected = sorted(
        {_within(workspace, source) for source in sources},
        key=lambda path: path.as_posix().casefold(),
    )
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            written: set[str] = set()
            for source in selected:
                if not source.exists() or source == destination or source == temporary:
                    continue
                candidates = [source] if source.is_file() else sorted(source.rglob("*"))
                for candidate in candidates:
                    if (
                        not candidate.is_file()
                        or candidate.is_symlink()
                        or candidate == destination
                        or candidate == temporary
                    ):
                        continue
                    candidate = _within(workspace, candidate)
                    arcname = candidate.relative_to(workspace).as_posix()
                    if arcname not in written:
                        archive.write(candidate, arcname)
                        written.add(arcname)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


__all__ = ["ArtifactError", "create_result_archive"]
