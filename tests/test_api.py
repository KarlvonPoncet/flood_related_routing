from __future__ import annotations

import json
from pathlib import Path
from urllib import error

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from shapely.geometry import Point

from api import config as config_module
from api import app as app_module
from api import routing as routing_module
from api.services import routing_service


def _json_response_payload(resp: JSONResponse) -> dict:
    return json.loads(resp.body.decode("utf-8"))


def _route_payload() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[14.5058, 46.0569], [15.9819, 45.8150]],
                },
                "properties": {"summary": {"distance": 1.0, "duration": 1.0}},
            }
        ],
    }


def test_health_returns_ok() -> None:
    assert app_module.health() == {"status": "ok"}


def test_frontend_returns_file_response_when_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = tmp_path / "index.html"
    index.write_text("<html><body>ok</body></html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "FRONTEND_INDEX", index)

    resp = app_module.frontend()

    assert isinstance(resp, FileResponse)
    assert Path(resp.path) == index


def test_frontend_raises_404_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.html"
    monkeypatch.setattr(app_module, "FRONTEND_INDEX", missing)

    with pytest.raises(HTTPException) as exc_info:
        app_module.frontend()

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Frontend not found"


def test_geojson_live_returns_existing_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "live.geojson"
    payload = {"type": "FeatureCollection", "features": []}
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(app_module, "DEFAULT_ARTIFACT", artifact)

    def _unexpected_ingest(source: str, target: str) -> Path:
        raise AssertionError("ingest_file should not be called when artifact exists")

    monkeypatch.setattr(app_module, "ingest_file", _unexpected_ingest)

    resp = app_module.geojson_live()

    assert isinstance(resp, JSONResponse)
    assert _json_response_payload(resp) == payload


def test_geojson_live_runs_ingestion_when_artifact_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "live.geojson"
    monkeypatch.setattr(app_module, "DEFAULT_ARTIFACT", artifact)

    observed: dict[str, str] = {}

    def _ingest(source: str, target: str) -> Path:
        observed["source"] = source
        observed["target"] = target
        payload = _route_payload()
        artifact.write_text(json.dumps(payload), encoding="utf-8")
        return artifact

    monkeypatch.setattr(app_module, "ingest_file", _ingest)

    resp = app_module.geojson_live(source="test-source")

    assert _json_response_payload(resp)["type"] == "FeatureCollection"
    assert observed == {"source": "test-source", "target": str(artifact)}


def test_geojson_live_raises_500_for_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "live.geojson"
    artifact.write_text("{invalid-json", encoding="utf-8")
    monkeypatch.setattr(app_module, "DEFAULT_ARTIFACT", artifact)

    with pytest.raises(HTTPException) as exc_info:
        app_module.geojson_live()

    assert exc_info.value.status_code == 500
    assert "Failed to read GeoJSON" in str(exc_info.value.detail)


def test_artifact_returns_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = tmp_path / "artifact.geojson"
    existing.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    def _unexpected_ingest(source: str, target: str) -> Path:
        raise AssertionError("ingest_file should not be called when target exists")

    monkeypatch.setattr(app_module, "ingest_file", _unexpected_ingest)

    resp = app_module.get_or_build_artifact(target=str(existing))

    assert isinstance(resp, FileResponse)
    assert Path(resp.path) == existing


def test_artifact_runs_ingestion_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "new.geojson"
    observed: dict[str, str] = {}

    def _ingest(source: str, target: str) -> Path:
        observed["source"] = source
        observed["target"] = target
        out = Path(target)
        out.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return out

    monkeypatch.setattr(app_module, "ingest_file", _ingest)

    resp = app_module.get_or_build_artifact(target=str(target), source="custom")

    assert isinstance(resp, FileResponse)
    assert Path(resp.path) == target
    assert observed == {"source": "custom", "target": str(target)}


def test_artifact_raises_500_when_ingestion_does_not_create_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "missing-output.geojson"

    def _ingest(source: str, target: str) -> Path:
        del source, target
        return tmp_path / "does-not-exist.geojson"

    monkeypatch.setattr(app_module, "ingest_file", _ingest)

    with pytest.raises(HTTPException) as exc_info:
        app_module.get_or_build_artifact(target=str(target))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Ingestion finished but output file is missing"


def test_artifact_rejects_parent_traversal_target() -> None:
    with pytest.raises(HTTPException) as exc_info:
        app_module.get_or_build_artifact(target="../secret.geojson")

    assert exc_info.value.status_code == 400
    assert "cannot contain '..'" in str(exc_info.value.detail)


def test_artifact_rejects_absolute_target_outside_allowed_roots() -> None:
    with pytest.raises(HTTPException) as exc_info:
        app_module.get_or_build_artifact(target="/etc/passwd")

    assert exc_info.value.status_code == 400
    assert "must be under one of" in str(exc_info.value.detail)


def test_route_endpoint_uses_ingestion_and_returns_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"

    observed: dict[str, object] = {}

    def _ingest(source: str, target: str) -> Path:
        observed["ingest_source"] = source
        observed["ingest_target"] = target
        artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return artifact

    monkeypatch.setattr(routing_module, "ingest_file", _ingest)

    fake_geometries = [object(), object()]
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: fake_geometries)

    avoid = {
        "type": "Polygon",
        "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.1, 46.1], [14.0, 46.0]]],
    }
    monkeypatch.setattr(routing_module, "_build_avoid_polygons", lambda geoms: avoid if geoms else None)

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        observed["start"] = (start.lat, start.lon)
        observed["end"] = (end.lat, end.lon)
        observed["avoid_polygons"] = avoid_polygons
        observed["radiuses"] = radiuses
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        source="route-source",
        artifact_path=str(artifact),
    )

    payload = routing_module.route_avoid_flood_high_risk(req)

    assert payload["artifact_path"] == str(artifact)
    assert payload["high_risk_polygon_count"] == 2
    assert payload["using_avoid_polygons"] is True
    assert payload["route"]["type"] == "FeatureCollection"
    assert observed["ingest_source"] == "route-source"
    assert observed["ingest_target"] == str(artifact)
    assert observed["avoid_polygons"] == avoid
    assert observed["radiuses"] is None


def test_route_endpoint_falls_back_when_ors_rejects_avoid_polygon_area(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])

    avoid = {
        "type": "Polygon",
        "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.1, 46.1], [14.0, 46.0]]],
    }
    monkeypatch.setattr(routing_module, "_build_avoid_polygons", lambda geoms: avoid if geoms else None)

    calls: list[dict] = []

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end
        calls.append({"avoid_polygons": avoid_polygons, "radiuses": radiuses})
        if avoid_polygons is not None:
            raise HTTPException(
                status_code=502,
                detail='OpenRouteService request failed (400): {"error":{"code":2003,"message":"The area of a polygon to avoid must not exceed 2.0E8 square meters."}}',
            )
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )
    payload = routing_module.route_avoid_flood_high_risk(req)

    assert len(calls) == 2
    assert calls[0]["avoid_polygons"] == avoid
    assert calls[1]["avoid_polygons"] is None
    assert calls[0]["radiuses"] is None
    assert calls[1]["radiuses"] is None
    assert payload["avoidance_polygon_count"] == 0
    assert payload["using_avoid_polygons"] is False
    assert payload["using_custom_radiuses"] is False
    assert "warning" in payload
    assert payload["route"]["type"] == "FeatureCollection"


def test_route_endpoint_retries_with_reduced_polygons_on_area_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()] * 200)

    def _build_avoid(geoms):
        if not geoms:
            return None
        return {"type": "Polygon", "count": len(geoms)}

    monkeypatch.setattr(routing_module, "_build_avoid_polygons", _build_avoid)

    calls: list[int] = []

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, radiuses
        count = avoid_polygons.get("count") if avoid_polygons else 0
        calls.append(count)
        if count > 50:
            raise HTTPException(
                status_code=502,
                detail='OpenRouteService request failed (400): {"error":{"code":2003,"message":"The area of a polygon to avoid must not exceed 2.0E8 square meters."}}',
            )
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )
    payload = routing_module.route_avoid_flood_high_risk(req)

    assert calls == [200, 100, 50]
    assert payload["high_risk_polygon_count"] == 200
    assert payload["avoidance_polygon_count"] == 50
    assert payload["using_avoid_polygons"] is True
    assert "retried with 100 nearest polygons" in payload["warning"]
    assert "retried with 50 nearest polygons" in payload["warning"]


def test_route_endpoint_retries_with_custom_radiuses_when_ors_reports_unroutable_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]},
    )

    calls: list[dict] = []

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons
        calls.append({"radiuses": radiuses})
        if radiuses is None:
            raise HTTPException(
                status_code=502,
                detail='OpenRouteService request failed (404): {"error":{"code":2010,"message":"Could not find routable point within a radius of 350.0 meters"}}',
            )
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    payload = routing_module.route_avoid_flood_high_risk(req)

    assert len(calls) == 2
    assert calls[0]["radiuses"] is None
    assert calls[1]["radiuses"] == [routing_module.get_settings().ors_fallback_radius_meters] * 2
    assert payload["using_custom_radiuses"] is True
    assert "warning" in payload
    assert payload["route"]["type"] == "FeatureCollection"


def test_route_endpoint_re_raises_non_retriable_ors_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]},
    )

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons, radiuses
        raise HTTPException(status_code=502, detail='OpenRouteService request failed (400): {"error":{"code":2099}}')

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 502
    assert '"code":2099' in str(exc_info.value.detail)


def test_route_endpoint_logs_timing_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object(), object(), object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "count": len(geoms)} if geoms else None,
    )
    monkeypatch.setattr(
        routing_module,
        "_call_routing_provider",
        lambda *, start, end, avoid_polygons, radiuses=None: _route_payload(),
    )

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    with caplog.at_level("INFO"):
        payload = routing_module.route_avoid_flood_high_risk(req)

    assert payload["route"]["type"] == "FeatureCollection"
    logs = "\n".join(caplog.messages)
    assert "route_request_started" in logs
    assert "route_request_prepared" in logs
    assert "high_risk_total=3 selected_for_avoidance=3" in logs
    assert "route_request_succeeded" in logs
    assert "total_ms=" in logs


def test_route_endpoint_logs_failure_timing_on_ors_502(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]},
    )

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons, radiuses
        raise HTTPException(status_code=502, detail='OpenRouteService request failed (400): {"error":{"code":2099}}')

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    with caplog.at_level("INFO"):
        with pytest.raises(HTTPException):
            routing_module.route_avoid_flood_high_risk(req)

    logs = "\n".join(caplog.messages)
    assert "route_request_started" in logs
    assert "route_request_failed" in logs
    assert "route_ms=" in logs
    assert "total_ms=" in logs


def test_route_endpoint_rejects_invalid_provider_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]},
    )
    monkeypatch.setattr(
        routing_module,
        "_call_routing_provider",
        lambda *, start, end, avoid_polygons, radiuses=None: {"routes": []},
    )

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 502
    assert "expected GeoJSON FeatureCollection" in str(exc_info.value.detail)


def test_route_endpoint_rejects_parent_traversal_artifact_path() -> None:
    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path="../secret.geojson",
    )

    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 400
    assert "cannot contain '..'" in str(exc_info.value.detail)


def test_route_endpoint_rejects_absolute_artifact_path_outside_allowed_roots() -> None:
    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path="/etc/passwd",
    )

    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 400
    assert "must be under one of" in str(exc_info.value.detail)


def test_route_endpoint_timeout_surfaces_reachability_detail(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORS_USE_LOCAL", "true")
    monkeypatch.setenv("ORS_REQUIRE_API_KEY", "false")
    monkeypatch.setenv(
        "ORS_LOCAL_DIRECTIONS_URL",
        "http://host.docker.internal:8080/ors/v2/directions/driving-car/geojson",
    )
    monkeypatch.setenv("ORS_REQUEST_TIMEOUT_SECONDS", "8")
    config_module.reload_settings()
    try:
        artifact = tmp_path / "flood.geojson"
        artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

        def _raise_timeout(req, timeout):
            del req, timeout
            raise error.URLError(TimeoutError("timed out"))

        monkeypatch.setattr(routing_service.request, "urlopen", _raise_timeout)

        req = routing_module.RouteAvoidFloodsRequest(
            start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
            end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
            artifact_path=str(artifact),
        )
        with pytest.raises(HTTPException) as exc_info:
            routing_module.route_avoid_flood_high_risk(req)

        assert exc_info.value.status_code == 502
        detail = str(exc_info.value.detail)
        assert "timed out after 8.0s" in detail
        assert "host.docker.internal:8080" in detail
        assert "reachable from the API container" in detail
    finally:
        config_module.reload_settings()


def test_route_endpoint_timeout_uses_configured_ors_timeout_seconds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ORS_USE_LOCAL", "true")
    monkeypatch.setenv("ORS_REQUIRE_API_KEY", "false")
    monkeypatch.setenv(
        "ORS_LOCAL_DIRECTIONS_URL",
        "http://host.docker.internal:8080/ors/v2/directions/driving-car/geojson",
    )
    monkeypatch.setenv("ORS_REQUEST_TIMEOUT_SECONDS", "3.5")
    config_module.reload_settings()
    try:
        artifact = tmp_path / "flood.geojson"
        artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        observed: dict[str, float] = {}

        def _raise_timeout(req, timeout):
            del req
            observed["timeout"] = timeout
            raise error.URLError(TimeoutError("timed out"))

        monkeypatch.setattr(routing_service.request, "urlopen", _raise_timeout)

        req = routing_module.RouteAvoidFloodsRequest(
            start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
            end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
            artifact_path=str(artifact),
        )
        with pytest.raises(HTTPException) as exc_info:
            routing_module.route_avoid_flood_high_risk(req)

        assert exc_info.value.status_code == 502
        assert observed["timeout"] == 3.5
        assert "timed out after 3.5s" in str(exc_info.value.detail)
    finally:
        config_module.reload_settings()


def test_route_endpoint_retries_without_avoid_polygons_on_distance_limit_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object(), object()])

    avoid = {
        "type": "Polygon",
        "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.1, 46.1], [14.0, 46.0]]],
    }
    monkeypatch.setattr(routing_module, "_build_avoid_polygons", lambda geoms: avoid if geoms else None)

    calls: list[dict] = []

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, radiuses
        calls.append({"avoid_polygons": avoid_polygons})
        if avoid_polygons is not None:
            raise HTTPException(
                status_code=502,
                detail=(
                    'OpenRouteService request failed (400): {"error":{"code":2004,'
                    '"message":"Request parameters exceed the server configuration limits. '
                    'The approximated route distance must not be greater than 100000.0 meters."}}'
                ),
            )
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )
    payload = routing_module.route_avoid_flood_high_risk(req)

    assert len(calls) == 2
    assert calls[0]["avoid_polygons"] is not None
    assert calls[1]["avoid_polygons"] is None
    assert payload["using_avoid_polygons"] is False
    assert payload["avoidance_polygon_count"] == 0
    assert "max distance constraint" in payload["warning"]


def test_route_endpoint_returns_422_when_route_exceeds_ors_distance_limit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [])
    monkeypatch.setattr(routing_module, "_build_avoid_polygons", lambda geoms: None)

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons, radiuses
        raise HTTPException(
            status_code=502,
            detail=(
                'OpenRouteService request failed (400): {"error":{"code":2004,'
                '"message":"Request parameters exceed the server configuration limits. '
                'The approximated route distance must not be greater than 100000.0 meters."}}'
            ),
        )

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )
    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 422
    assert "maximum distance (100000 meters)" in str(exc_info.value.detail)


def test_route_endpoint_selects_nearest_200_polygons_to_midpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    far_geometries = [Point(1000 + i, 0).buffer(0.01) for i in range(200)]
    near_geometries = [Point(i, 0).buffer(0.01) for i in range(10)]
    all_geometries = far_geometries + near_geometries

    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: all_geometries)

    observed: dict[str, object] = {}

    def _build_avoid(geoms):
        selected_centers = sorted(round(g.centroid.x) for g in geoms)
        observed["selected_centers"] = selected_centers
        return {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]}

    monkeypatch.setattr(routing_module, "_build_avoid_polygons", _build_avoid)

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, radiuses
        observed["avoid_polygons"] = avoid_polygons
        return _route_payload()

    monkeypatch.setattr(routing_module, "_call_routing_provider", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=-1.0, lon=-1.0),
        end=routing_module.Coordinate(lat=1.0, lon=1.0),
        artifact_path=str(artifact),
    )
    payload = routing_module.route_avoid_flood_high_risk(req)

    selected_centers = observed["selected_centers"]
    assert isinstance(selected_centers, list)
    assert len(selected_centers) == 200
    assert selected_centers[:10] == list(range(10))
    assert 1190 not in selected_centers
    assert 1199 not in selected_centers
    assert payload["high_risk_polygon_count"] == 200
    assert payload["using_avoid_polygons"] is True
    assert payload["route"]["type"] == "FeatureCollection"
    assert observed["avoid_polygons"] is not None
