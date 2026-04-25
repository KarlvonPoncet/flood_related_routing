from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse, JSONResponse
from shapely.geometry import Point

from api import app as app_module
from api import routing as routing_module


def _json_response_payload(resp: JSONResponse) -> dict:
    return json.loads(resp.body.decode("utf-8"))


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
        payload = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
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


def test_route_endpoint_uses_ingestion_and_returns_route_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    monkeypatch.setattr(routing_module, "DEFAULT_ARTIFACT", artifact)

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
        return {"type": "FeatureCollection", "features": [{"type": "Feature"}]}

    monkeypatch.setattr(routing_module, "_call_openrouteservice", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        source="route-source",
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
    monkeypatch.setattr(routing_module, "DEFAULT_ARTIFACT", artifact)
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
        return {"type": "FeatureCollection", "features": [{"type": "Feature"}]}

    monkeypatch.setattr(routing_module, "_call_openrouteservice", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
    )
    payload = routing_module.route_avoid_flood_high_risk(req)

    assert len(calls) == 2
    assert calls[0]["avoid_polygons"] == avoid
    assert calls[1]["avoid_polygons"] is None
    assert calls[0]["radiuses"] is None
    assert calls[1]["radiuses"] is None
    assert payload["using_avoid_polygons"] is False
    assert payload["using_custom_radiuses"] is False
    assert "warning" in payload
    assert payload["route"]["type"] == "FeatureCollection"


def test_route_endpoint_retries_with_custom_radiuses_when_ors_reports_unroutable_point(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "DEFAULT_ARTIFACT", artifact)
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
        return {"type": "FeatureCollection", "features": [{"type": "Feature"}]}

    monkeypatch.setattr(routing_module, "_call_openrouteservice", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
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
    monkeypatch.setattr(routing_module, "DEFAULT_ARTIFACT", artifact)
    monkeypatch.setattr(routing_module, "_load_high_risk_geometries", lambda p: [object()])
    monkeypatch.setattr(
        routing_module,
        "_build_avoid_polygons",
        lambda geoms: {"type": "Polygon", "coordinates": [[[14.0, 46.0], [14.1, 46.0], [14.0, 46.1], [14.0, 46.0]]]},
    )

    def _call_ors(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons, radiuses
        raise HTTPException(status_code=502, detail='OpenRouteService request failed (400): {"error":{"code":2099}}')

    monkeypatch.setattr(routing_module, "_call_openrouteservice", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
    )

    with pytest.raises(HTTPException) as exc_info:
        routing_module.route_avoid_flood_high_risk(req)

    assert exc_info.value.status_code == 502
    assert '"code":2099' in str(exc_info.value.detail)


def test_route_endpoint_selects_nearest_200_polygons_to_midpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / "flood.geojson"
    artifact.write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
    monkeypatch.setattr(routing_module, "DEFAULT_ARTIFACT", artifact)

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
        return {"type": "FeatureCollection", "features": [{"type": "Feature"}]}

    monkeypatch.setattr(routing_module, "_call_openrouteservice", _call_ors)

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=-1.0, lon=-1.0),
        end=routing_module.Coordinate(lat=1.0, lon=1.0),
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
