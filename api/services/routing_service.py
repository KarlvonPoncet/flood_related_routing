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


def load_high_risk_geometries(artifact_path: Path, *, max_avoid_polygons: int) -> list[Any]:
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
        if len(geometries) >= max_avoid_polygons:
            break

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
    api_key = get_settings().ors_api_key
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing ORS_API_KEY environment variable")

    body: dict[str, Any] = {
        "coordinates": [
            [start.lon, start.lat],
            [end.lon, end.lat],
        ],
    }
    if radiuses is not None:
        body["radiuses"] = radiuses
    if avoid_polygons is not None:
        body["options"] = {"avoid_polygons": avoid_polygons}

    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        get_settings().ors_directions_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": api_key,
            "Content-Type": "application/json",
            "Accept": "application/geo+json, application/json",
        },
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
        return json.loads(response_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid OpenRouteService response: {exc}") from exc


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
    avoid_polygons = build_avoid_fn(geometries)
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
                avoid_polygons = None
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
        "using_avoid_polygons": avoid_polygons is not None,
        "using_custom_radiuses": radiuses is not None,
        "route": route,
    }
    if route_warnings:
        response["warning"] = " ".join(route_warnings)
    return response
