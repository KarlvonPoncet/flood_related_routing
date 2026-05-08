from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

from api.services import artifact_service


def test_ensure_output_file_returns_503_when_request_ingestion_disabled(tmp_path: Path) -> None:
    target = tmp_path / "missing.geojson"

    with pytest.raises(HTTPException) as exc_info:
        artifact_service.ensure_output_file(
            target_path=target,
            source="default",
            ingest_fn=lambda source, target: Path(target),
            allow_request_ingestion=False,
        )

    assert exc_info.value.status_code == 503
    assert "request-triggered ingestion is disabled" in str(exc_info.value.detail)


def test_ensure_output_file_collapses_concurrent_ingestion_for_same_path(tmp_path: Path) -> None:
    target = tmp_path / "live.geojson"
    calls = {"count": 0}
    calls_lock = threading.Lock()
    release_event = threading.Event()

    def _ingest(source: str, target: str) -> Path:
        del source
        with calls_lock:
            calls["count"] += 1
        # Keep the first caller in-flight to force overlap.
        release_event.wait(timeout=2.0)
        out = Path(target)
        out.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return out

    results: list[Path] = []
    errors: list[Exception] = []

    def _worker() -> None:
        try:
            result = artifact_service.ensure_output_file(
                target_path=target,
                source="default",
                ingest_fn=_ingest,
                allow_request_ingestion=True,
            )
            results.append(result)
        except Exception as exc:  # pragma: no cover - assertion below validates no errors
            errors.append(exc)

    t1 = threading.Thread(target=_worker, daemon=True)
    t2 = threading.Thread(target=_worker, daemon=True)
    t1.start()
    time.sleep(0.05)
    t2.start()
    time.sleep(0.05)
    release_event.set()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)

    assert not errors
    assert len(results) == 2
    assert all(path == target for path in results)
    assert calls["count"] == 1
