from __future__ import annotations

from pathlib import Path

import pytest

from api import config


def test_get_settings_uses_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ROOT_DIR", "/tmp/flood-app")
    monkeypatch.setenv("DEFAULT_ARTIFACT_PATH", "/tmp/custom/live.geojson")
    monkeypatch.setenv("FRONTEND_INDEX_PATH", "/tmp/custom/index.html")
    monkeypatch.setenv("ORS_API_KEY", "secret-key")
    monkeypatch.setenv("ORS_DIRECTIONS_URL", "https://remote.example/route")
    monkeypatch.setenv("ORS_REQUEST_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("ROUTING_PROVIDER", "OpenRouteService")
    monkeypatch.setenv("CUSTOM_ROUTING_GRAPH_PATH", "/tmp/custom/graph.graphml")
    monkeypatch.setenv("CUSTOM_ROUTING_GRAPH_METADATA_PATH", "/tmp/custom/graph-meta.json")
    monkeypatch.setenv("CUSTOM_ROUTING_OSM_PLACE", "Slovenia")
    monkeypatch.setenv("CUSTOM_ROUTING_OSM_NETWORK_TYPE", "bike")
    monkeypatch.setenv("CUSTOM_ROUTING_SIMPLIFY_GRAPH", "false")
    monkeypatch.setenv("ALLOW_REQUEST_INGESTION", "true")
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://frontend.example,https://admin.example")
    monkeypatch.setenv("MAX_AVOID_POLYGONS", "123")
    monkeypatch.setenv("SIMPLIFY_TOLERANCE_DEGREES", "0.25")
    monkeypatch.setenv("EU_MIN_LAT", "10.0")

    config.reload_settings()
    settings = config.get_settings()

    assert settings.root_dir == Path("/tmp/flood-app")
    assert settings.default_artifact == Path("/tmp/custom/live.geojson")
    assert settings.frontend_index == Path("/tmp/custom/index.html")
    assert settings.ors_api_key == "secret-key"
    assert settings.ors_directions_url == "https://remote.example/route"
    assert settings.ors_request_timeout_seconds == 7.5
    assert settings.routing_provider == "openrouteservice"
    assert settings.custom_routing_graph_path == Path("/tmp/custom/graph.graphml")
    assert settings.custom_routing_graph_metadata_path == Path("/tmp/custom/graph-meta.json")
    assert settings.custom_routing_osm_place == "Slovenia"
    assert settings.custom_routing_osm_network_type == "bike"
    assert settings.custom_routing_simplify_graph is False
    assert settings.allow_request_ingestion is True
    assert settings.cors_allow_origins == ("https://frontend.example", "https://admin.example")
    assert settings.max_avoid_polygons == 123
    assert settings.simplify_tolerance_degrees == 0.25
    assert settings.eu_min_lat == 10.0


def test_get_settings_raises_on_invalid_numeric_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_AVOID_POLYGONS", "not-an-int")
    config.reload_settings()

    with pytest.raises(ValueError, match="MAX_AVOID_POLYGONS must be an integer"):
        config.get_settings()

    config.reload_settings()


def test_get_settings_prefers_local_ors_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_DIRECTIONS_URL", "https://remote.example/route")
    monkeypatch.setenv("ORS_LOCAL_DIRECTIONS_URL", "http://127.0.0.1:8080/ors/v2/directions/driving-car/geojson")
    monkeypatch.setenv("ORS_USE_LOCAL", "true")
    config.reload_settings()

    settings = config.get_settings()
    assert settings.ors_use_local is True
    assert settings.ors_local_directions_url == "http://127.0.0.1:8080/ors/v2/directions/driving-car/geojson"
    assert settings.ors_directions_url == "http://127.0.0.1:8080/ors/v2/directions/driving-car/geojson"
    assert settings.ors_require_api_key is False

    config.reload_settings()


def test_get_settings_raises_on_invalid_boolean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORS_USE_LOCAL", "sometimes")
    config.reload_settings()

    with pytest.raises(ValueError, match="ORS_USE_LOCAL must be a boolean"):
        config.get_settings()

    config.reload_settings()


def test_get_settings_defaults_request_ingestion_to_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALLOW_REQUEST_INGESTION", raising=False)
    config.reload_settings()

    settings = config.get_settings()
    assert settings.allow_request_ingestion is False

    config.reload_settings()


def test_get_settings_defaults_cors_to_local_dev_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORS_ALLOW_ORIGINS", raising=False)
    config.reload_settings()

    settings = config.get_settings()
    assert "http://127.0.0.1:8000" in settings.cors_allow_origins
    assert "http://localhost:5173" in settings.cors_allow_origins

    config.reload_settings()


def test_get_settings_rejects_empty_cors_origin_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " ,  , ")
    config.reload_settings()

    with pytest.raises(ValueError, match="CORS_ALLOW_ORIGINS must contain at least one origin"):
        config.get_settings()

    config.reload_settings()
