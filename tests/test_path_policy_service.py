from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.config import get_settings
from api.services import path_policy_service


def test_resolve_artifact_path_accepts_default_processed_root() -> None:
    settings = get_settings()
    path = path_policy_service.resolve_artifact_path(
        settings.default_artifact.parent / "safe.geojson",
        settings=settings,
    )

    assert path == (settings.default_artifact.parent / "safe.geojson").resolve(strict=False)


def test_resolve_artifact_path_accepts_system_tmp(tmp_path: Path) -> None:
    settings = get_settings()
    path = path_policy_service.resolve_artifact_path(tmp_path / "safe.geojson", settings=settings)

    assert path == (tmp_path / "safe.geojson").resolve(strict=False)


def test_resolve_artifact_path_rejects_parent_traversal() -> None:
    settings = get_settings()

    with pytest.raises(HTTPException) as exc_info:
        path_policy_service.resolve_artifact_path("../secrets.geojson", settings=settings)

    assert exc_info.value.status_code == 400
    assert "cannot contain '..'" in str(exc_info.value.detail)


def test_resolve_artifact_path_rejects_absolute_path_outside_allowed_roots() -> None:
    settings = get_settings()

    with pytest.raises(HTTPException) as exc_info:
        path_policy_service.resolve_artifact_path("/etc/passwd", settings=settings)

    assert exc_info.value.status_code == 400
    assert "must be under one of" in str(exc_info.value.detail)
