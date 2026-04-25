from __future__ import annotations

from pathlib import Path

import pytest

from api import config


def test_get_settings_uses_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ROOT_DIR", "/tmp/flood-app")
    monkeypatch.setenv("DEFAULT_ARTIFACT_PATH", "/tmp/custom/live.geojson")
    monkeypatch.setenv("FRONTEND_INDEX_PATH", "/tmp/custom/index.html")
    monkeypatch.setenv("ORS_API_KEY", "secret-key")
    monkeypatch.setenv("MAX_AVOID_POLYGONS", "123")
    monkeypatch.setenv("SIMPLIFY_TOLERANCE_DEGREES", "0.25")
    monkeypatch.setenv("EU_MIN_LAT", "10.0")

    config.reload_settings()
    settings = config.get_settings()

    assert settings.root_dir == Path("/tmp/flood-app")
    assert settings.default_artifact == Path("/tmp/custom/live.geojson")
    assert settings.frontend_index == Path("/tmp/custom/index.html")
    assert settings.ors_api_key == "secret-key"
    assert settings.max_avoid_polygons == 123
    assert settings.simplify_tolerance_degrees == 0.25
    assert settings.eu_min_lat == 10.0


def test_get_settings_raises_on_invalid_numeric_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_AVOID_POLYGONS", "not-an-int")
    config.reload_settings()

    with pytest.raises(ValueError, match="MAX_AVOID_POLYGONS must be an integer"):
        config.get_settings()

    config.reload_settings()
