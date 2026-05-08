from __future__ import annotations

from pathlib import Path
from urllib import error
from urllib import request as urllib_request

import pytest
from fastapi import HTTPException

from api.services import routing_service


def test_geojson_to_json_url_rewrites_suffix() -> None:
    assert (
        routing_service._geojson_to_json_url(
            "http://localhost:8080/ors/v2/directions/driving-car/geojson"
        )
        == "http://localhost:8080/ors/v2/directions/driving-car/json"
    )


def test_geojson_to_json_url_leaves_other_urls_unchanged() -> None:
    url = "http://localhost:8080/ors/v2/directions/driving-car/json"
    assert routing_service._geojson_to_json_url(url) == url


def test_normalize_ors_route_payload_passes_feature_collection_through() -> None:
    payload = {"type": "FeatureCollection", "features": [{"type": "Feature"}]}
    assert routing_service._normalize_ors_route_payload(payload) == payload


def test_normalize_ors_route_payload_converts_json_route_geometry_list() -> None:
    payload = {
        "routes": [
            {
                "geometry": [[14.5, 46.0], [14.6, 46.1]],
                "summary": {"distance": 1000.0, "duration": 120.0},
            }
        ]
    }
    out = routing_service._normalize_ors_route_payload(payload)
    assert out["type"] == "FeatureCollection"
    assert out["features"][0]["geometry"]["type"] == "LineString"
    assert out["features"][0]["properties"]["summary"]["distance"] == 1000.0


def test_normalize_ors_route_payload_converts_json_route_geometry_object() -> None:
    payload = {
        "routes": [
            {
                "geometry": {"type": "LineString", "coordinates": [[14.5, 46.0], [14.6, 46.1]]},
                "summary": {"distance": 900.0, "duration": 100.0},
            }
        ]
    }
    out = routing_service._normalize_ors_route_payload(payload)
    assert out["type"] == "FeatureCollection"
    assert out["features"][0]["geometry"]["coordinates"][0] == [14.5, 46.0]


def test_is_ors_unsupported_format_error_detects_code_2007() -> None:
    exc = HTTPException(
        status_code=502,
        detail='OpenRouteService request failed (406): {"error":{"code":2007,"message":"This response format is not supported"}}',
    )
    assert routing_service._is_ors_unsupported_format_error(exc) is True


def test_is_ors_distance_limit_error_detects_code_2004() -> None:
    exc = HTTPException(
        status_code=502,
        detail=(
            'OpenRouteService request failed (400): {"error":{"code":2004,'
            '"message":"Request parameters exceed the server configuration limits. '
            'The approximated route distance must not be greater than 100000.0 meters."}}'
        ),
    )
    assert routing_service.is_ors_distance_limit_error(exc) is True


def test_to_provider_error_maps_ors_codes_to_structured_exceptions() -> None:
    area_exc = HTTPException(
        status_code=502,
        detail='OpenRouteService request failed (400): {"error":{"code":2003,"message":"The area of a polygon to avoid must not exceed 2.0E8 square meters."}}',
    )
    unroutable_exc = HTTPException(
        status_code=502,
        detail='OpenRouteService request failed (404): {"error":{"code":2010,"message":"Could not find routable point within a radius of 350.0 meters"}}',
    )
    distance_exc = HTTPException(
        status_code=502,
        detail=(
            'OpenRouteService request failed (400): {"error":{"code":2004,'
            '"message":"Request parameters exceed the server configuration limits. '
            'The approximated route distance must not be greater than 100000.0 meters."}}'
        ),
    )

    mapped_area = routing_service._to_provider_error(area_exc)
    mapped_unroutable = routing_service._to_provider_error(unroutable_exc)
    mapped_distance = routing_service._to_provider_error(distance_exc)

    assert isinstance(mapped_area, routing_service.AvoidAreaError)
    assert isinstance(mapped_unroutable, routing_service.UnroutablePointError)
    assert isinstance(mapped_distance, routing_service.DistanceLimitError)
    assert mapped_distance.max_distance_meters == 100000.0


def test_get_routing_provider_returns_openrouteservice_by_default() -> None:
    provider = routing_service.get_routing_provider()
    assert provider.name == "openrouteservice"


def test_get_routing_provider_rejects_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROUTING_PROVIDER", "unknown")
    routing_service.get_settings.cache_clear()
    try:
        with pytest.raises(HTTPException) as exc_info:
            routing_service.get_routing_provider()
    finally:
        routing_service.get_settings.cache_clear()

    assert exc_info.value.status_code == 500
    assert "Unsupported ROUTING_PROVIDER" in str(exc_info.value.detail)


def test_compute_flood_aware_route_logs_attempts_and_area_fallback(caplog: pytest.LogCaptureFixture) -> None:
    class _Coordinate:
        def __init__(self, lat: float, lon: float):
            self.lat = lat
            self.lon = lon

    def _build_avoid(geometries):
        if not geometries:
            return None
        return {"type": "Polygon", "count": len(geometries)}

    attempts: list[int] = []

    def _call_route(*, start, end, avoid_polygons, radiuses=None):
        del start, end, radiuses
        count = avoid_polygons.get("count") if avoid_polygons else 0
        attempts.append(count)
        if count > 1:
            raise routing_service.AvoidAreaError("avoid polygon area too large")
        return {"type": "FeatureCollection", "features": [{"type": "Feature"}]}

    with caplog.at_level("INFO"):
        response = routing_service.compute_flood_aware_route(
            start=_Coordinate(lat=46.0, lon=14.0),
            end=_Coordinate(lat=45.0, lon=15.0),
            artifact_path=Path("/tmp/ignored.geojson"),
            load_geometries_fn=lambda _: [object(), object(), object(), object()],
            build_avoid_fn=_build_avoid,
            call_route_fn=_call_route,
            fallback_radius_meters=2000.0,
        )

    assert attempts == [4, 2, 1]
    assert response["avoidance_polygon_count"] == 1
    logs = "\n".join(caplog.messages)
    assert "flood_route_attempt_started attempt=1" in logs
    assert "flood_route_attempt_failed attempt=1" in logs
    assert "flood_route_retrying_with_fewer_polygons next_active_polygons=2" in logs
    assert "flood_route_completed attempts=3" in logs


def test_post_ors_json_timeout_error_includes_reachability_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_timeout(req, timeout):
        del req, timeout
        raise error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib_request, "urlopen", _raise_timeout)

    with pytest.raises(HTTPException) as exc_info:
        routing_service._post_ors_json(
            url="http://host.docker.internal:8080/ors/v2/directions/driving-car/geojson",
            body={"coordinates": [[14.5, 46.0], [14.6, 46.1]]},
            headers={"Content-Type": "application/json"},
            timeout_seconds=5.0,
        )

    detail = str(exc_info.value.detail)
    assert exc_info.value.status_code == 502
    assert "timed out after 5.0s" in detail
    assert "host.docker.internal:8080" in detail
    assert "reachable from the API container" in detail


def test_compute_flood_aware_route_returns_422_on_distance_limit_without_avoidance() -> None:
    class _Coordinate:
        def __init__(self, lat: float, lon: float):
            self.lat = lat
            self.lon = lon

    def _call_route(*, start, end, avoid_polygons, radiuses=None):
        del start, end, avoid_polygons, radiuses
        raise routing_service.DistanceLimitError("distance limit exceeded", max_distance_meters=100000.0)

    with pytest.raises(HTTPException) as exc_info:
        routing_service.compute_flood_aware_route(
            start=_Coordinate(lat=46.0, lon=14.0),
            end=_Coordinate(lat=45.0, lon=15.0),
            artifact_path=Path("/tmp/ignored.geojson"),
            load_geometries_fn=lambda _: [],
            build_avoid_fn=lambda geoms: None,
            call_route_fn=_call_route,
            fallback_radius_meters=2000.0,
        )

    assert exc_info.value.status_code == 422
    assert "maximum distance (100000 meters)" in str(exc_info.value.detail)
