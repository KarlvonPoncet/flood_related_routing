from __future__ import annotations

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
