from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib import error, request

from fastapi import HTTPException
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

from api.config import get_settings


class CoordinateLike(Protocol):
    lat: float
    lon: float


def load_high_risk_geometries(artifact_path: Path) -> list[Any]:
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read flood artifact: {exc}") from exc

    features = payload.get("features", [])
    geometries: list[Any] = []

    for feature in features:
        properties = feature.get("properties", {})
        if properties.get("risk_level") != "high":
            continue

        geometry = feature.get("geometry")
        if not geometry:
            continue

        try:
            parsed_geometry = shape(geometry)
        except Exception:
            continue

        if parsed_geometry.is_empty:
            continue

        if parsed_geometry.geom_type not in {"Polygon", "MultiPolygon"}:
            continue

        geometries.append(parsed_geometry)

    return geometries


def build_avoid_polygons(geometries: list[Any], *, simplify_tolerance_degrees: float) -> dict[str, Any] | None:
    if not geometries:
        return None

    merged = unary_union(geometries)
    if merged.is_empty:
        return None

    simplified = merged.simplify(simplify_tolerance_degrees, preserve_topology=True)
    if simplified.is_empty:
        return None

    if isinstance(simplified, GeometryCollection):
        keep = [g for g in simplified.geoms if g.geom_type in {"Polygon", "MultiPolygon"} and not g.is_empty]
        if not keep:
            return None
        simplified = unary_union(keep)

    if simplified.geom_type not in {"Polygon", "MultiPolygon"}:
        return None

    return mapping(simplified)


def call_openrouteservice(
    *,
    start: CoordinateLike,
    end: CoordinateLike,
    avoid_polygons: dict[str, Any] | None,
    radiuses: list[float] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.ors_use_local and not settings.ors_local_directions_url:
        raise HTTPException(
            status_code=500,
            detail="ORS_USE_LOCAL is enabled but ORS_LOCAL_DIRECTIONS_URL is not set",
        )

    api_key = settings.ors_api_key
    if settings.ors_require_api_key and not api_key:
        raise HTTPException(status_code=500, detail="Missing ORS_API_KEY environment variable")

    base_body: dict[str, Any] = {
        "coordinates": [
            [start.lon, start.lat],
            [end.lon, end.lat],
        ],
    }
    if radiuses is not None:
        base_body["radiuses"] = radiuses
    if avoid_polygons is not None:
        base_body["options"] = {"avoid_polygons": avoid_polygons}

    try:
        response_payload = _post_ors_json(
            url=settings.ors_directions_url,
            body=base_body,
            headers=_ors_headers(api_key),
        )
    except HTTPException as exc:
        if settings.ors_use_local and _is_ors_unsupported_format_error(exc):
            local_json_url = _geojson_to_json_url(settings.ors_directions_url)
            fallback_body = dict(base_body)
            fallback_body["geometry_format"] = "geojson"
            response_payload = _post_ors_json(
                url=local_json_url,
                body=fallback_body,
                headers=_ors_headers(api_key),
            )
        else:
            raise

    return _normalize_ors_route_payload(response_payload)


def is_ors_avoid_polygon_area_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2003" in detail and "polygon to avoid" in detail


def is_ors_unroutable_point_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2010" in detail and "routable point" in detail


def _is_ors_unsupported_format_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2007" in detail and "format is not supported" in detail


def _geojson_to_json_url(url: str) -> str:
    if url.endswith("/geojson"):
        return f"{url[:-8]}/json"
    return url


def _post_ors_json(*, url: str, body: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers=headers,
    )

    try:
        with request.urlopen(req, timeout=45) as response:
            response_bytes = response.read()
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouteService request failed ({exc.code}): {error_body}",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouteService request failed: {exc}") from exc

    try:
        parsed = json.loads(response_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid OpenRouteService response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Invalid OpenRouteService response: expected JSON object")
    return parsed


def _normalize_ors_route_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") == "FeatureCollection":
        return payload

    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        return payload

    first_route = routes[0]
    if not isinstance(first_route, dict):
        return payload

    geometry = first_route.get("geometry")
    normalized_geometry: dict[str, Any] | None = None
    if isinstance(geometry, dict) and geometry.get("type") and geometry.get("coordinates"):
        normalized_geometry = geometry
    elif isinstance(geometry, list):
        normalized_geometry = {"type": "LineString", "coordinates": geometry}

    if normalized_geometry is None:
        return payload

    summary = first_route.get("summary", {})
    feature = {
        "type": "Feature",
        "geometry": normalized_geometry,
        "properties": {
            "summary": summary if isinstance(summary, dict) else {},
        },
    }
    return {
        "type": "FeatureCollection",
        "features": [feature],
    }


def _ors_headers(api_key: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/geo+json, application/json",
    }
    if api_key:
        headers["Authorization"] = api_key
    return headers


def compute_flood_aware_route(
    *,
    start: CoordinateLike,
    end: CoordinateLike,
    artifact_path: Path,
    load_geometries_fn: Callable[[Path], list[Any]],
    build_avoid_fn: Callable[[list[Any]], dict[str, Any] | None],
    call_ors_fn: Callable[..., dict[str, Any]],
    fallback_radius_meters: float,
    area_error_fn: Callable[[HTTPException], bool],
    unroutable_error_fn: Callable[[HTTPException], bool],
) -> dict[str, Any]:
    geometries = load_geometries_fn(artifact_path)
    active_geometry_count = len(geometries)
    avoid_polygons = build_avoid_fn(geometries)
    if avoid_polygons is None:
        active_geometry_count = 0
    route_warnings: list[str] = []
    radiuses: list[float] | None = None

    while True:
        try:
            route = call_ors_fn(
                start=start,
                end=end,
                avoid_polygons=avoid_polygons,
                radiuses=radiuses,
            )
            break
        except HTTPException as exc:
            if avoid_polygons is not None and area_error_fn(exc):
                next_geometry_count = active_geometry_count // 2
                next_avoid_polygons: dict[str, Any] | None = None

                while next_geometry_count > 0:
                    candidate = build_avoid_fn(geometries[:next_geometry_count])
                    if candidate is not None:
                        next_avoid_polygons = candidate
                        break
                    next_geometry_count //= 2

                if next_avoid_polygons is not None:
                    active_geometry_count = next_geometry_count
                    avoid_polygons = next_avoid_polygons
                    route_warnings.append(
                        f"ORS rejected avoid_polygons area; retried with {active_geometry_count} nearest polygons."
                    )
                    continue

                avoid_polygons = None
                active_geometry_count = 0
                route_warnings.append(
                    "ORS rejected avoid_polygons due to area limit; returned route without flood avoidance polygons."
                )
                continue

            if radiuses is None and unroutable_error_fn(exc):
                radiuses = [fallback_radius_meters, fallback_radius_meters]
                route_warnings.append(
                    f"ORS could not snap one or more waypoints with default radius; retried with {fallback_radius_meters:.0f}m radiuses."
                )
                continue

            raise

    response = {
        "artifact_path": str(artifact_path),
        "high_risk_polygon_count": len(geometries),
        "avoidance_polygon_count": active_geometry_count,
        "using_avoid_polygons": avoid_polygons is not None,
        "using_custom_radiuses": radiuses is not None,
        "route": route,
    }
    if route_warnings:
        response["warning"] = " ".join(route_warnings)
    return response
