from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException

from api.config import Settings


def resolve_artifact_path(raw_path: str | Path, *, settings: Settings) -> Path:
    path = Path(raw_path)
    if _has_parent_traversal(path):
        raise HTTPException(status_code=400, detail="Artifact path cannot contain '..'")

    candidate = path.expanduser()
    if not candidate.is_absolute():
        candidate = settings.root_dir / candidate

    resolved = candidate.resolve(strict=False)
    allowed_roots = _artifact_allowed_roots(settings)

    if not _is_relative_to_any(resolved, allowed_roots):
        allowed = ", ".join(str(root) for root in allowed_roots)
        raise HTTPException(
            status_code=400,
            detail=f"Artifact path must be under one of: {allowed}",
        )

    return resolved


def _artifact_allowed_roots(settings: Settings) -> tuple[Path, ...]:
    roots = {
        settings.default_artifact.parent,
        settings.root_dir / "data/processed",
        settings.root_dir / "tmp",
        Path(tempfile.gettempdir()),
    }
    return tuple(sorted((root.resolve(strict=False) for root in roots), key=str))


def _has_parent_traversal(path: Path) -> bool:
    return ".." in path.parts


def _is_relative_to_any(path: Path, roots: Iterable[Path]) -> bool:
    for root in roots:
        if path == root or path.is_relative_to(root):
            return True
    return False
