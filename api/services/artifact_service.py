from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from fastapi import HTTPException


IngestFn = Callable[[str, str], Path]


def ensure_artifact_exists(*, artifact_path: Path, source: str, ingest_fn: IngestFn) -> Path:
    if artifact_path.exists() and artifact_path.is_file():
        return artifact_path

    created_path = ingest_fn(source=source, target=str(artifact_path))
    _assert_file_exists(created_path, error_detail="Ingestion finished but output file is missing")
    return created_path


def load_geojson_payload(artifact_path: Path) -> dict:
    try:
        return json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read GeoJSON: {exc}") from exc


def ensure_output_file(*, target_path: Path, source: str, ingest_fn: IngestFn) -> Path:
    if target_path.exists() and target_path.is_file():
        return target_path

    created_path = ingest_fn(source=source, target=str(target_path))
    _assert_file_exists(created_path, error_detail="Ingestion finished but output file is missing")
    return created_path


def _assert_file_exists(path: Path, *, error_detail: str) -> None:
    if path.exists() and path.is_file():
        return
    raise HTTPException(status_code=500, detail=error_detail)
