from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Callable

from fastapi import HTTPException


IngestFn = Callable[[str, str], Path]
_INGESTION_LOCKS_GUARD = threading.Lock()
_INGESTION_LOCKS: dict[Path, threading.Lock] = {}


def ensure_artifact_exists(
    *,
    artifact_path: Path,
    source: str,
    ingest_fn: IngestFn,
    allow_request_ingestion: bool,
) -> Path:
    if artifact_path.exists() and artifact_path.is_file():
        return artifact_path

    if not allow_request_ingestion:
        raise HTTPException(
            status_code=503,
            detail=(
                "Artifact is missing and request-triggered ingestion is disabled. "
                "Enable ALLOW_REQUEST_INGESTION=true or run the scheduler/background ingestion."
            ),
        )
    return _ingest_with_lock(artifact_path=artifact_path, source=source, ingest_fn=ingest_fn)


def load_geojson_payload(artifact_path: Path) -> dict:
    try:
        return json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read GeoJSON: {exc}") from exc


def ensure_output_file(
    *,
    target_path: Path,
    source: str,
    ingest_fn: IngestFn,
    allow_request_ingestion: bool,
) -> Path:
    if target_path.exists() and target_path.is_file():
        return target_path

    if not allow_request_ingestion:
        raise HTTPException(
            status_code=503,
            detail=(
                "Artifact is missing and request-triggered ingestion is disabled. "
                "Enable ALLOW_REQUEST_INGESTION=true or run the scheduler/background ingestion."
            ),
        )
    return _ingest_with_lock(artifact_path=target_path, source=source, ingest_fn=ingest_fn)


def _ingest_with_lock(*, artifact_path: Path, source: str, ingest_fn: IngestFn) -> Path:
    lock = _get_ingestion_lock(artifact_path)
    with lock:
        if artifact_path.exists() and artifact_path.is_file():
            return artifact_path
        created_path = ingest_fn(source=source, target=str(artifact_path))
        _assert_file_exists(created_path, error_detail="Ingestion finished but output file is missing")
        return created_path


def _get_ingestion_lock(artifact_path: Path) -> threading.Lock:
    key = artifact_path.resolve(strict=False)
    with _INGESTION_LOCKS_GUARD:
        lock = _INGESTION_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _INGESTION_LOCKS[key] = lock
        return lock


def _assert_file_exists(path: Path, *, error_detail: str) -> None:
    if path.exists() and path.is_file():
        return
    raise HTTPException(status_code=500, detail=error_detail)
