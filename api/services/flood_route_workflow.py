from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable
from uuid import uuid4

from fastapi import HTTPException

from api.config import Settings
from api.services import artifact_service, polygon_selection_service, routing_service


LOGGER = logging.getLogger(__name__)

IngestFn = Callable[[str, str], Path]
LoadGeometriesFn = Callable[[Path], list[Any]]
BuildAvoidFn = Callable[[list[Any]], dict[str, Any] | None]
CallRouteFn = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class FloodRouteInput:
    start: routing_service.CoordinateLike
    end: routing_service.CoordinateLike
    source: str
    artifact_path: Path | None


@dataclass(frozen=True)
class FloodRouteDependencies:
    ingest_fn: IngestFn
    load_geometries_fn: LoadGeometriesFn = routing_service.load_high_risk_geometries
    build_avoid_fn: BuildAvoidFn | None = None
    call_route_fn: CallRouteFn | None = None
    routing_provider: routing_service.RoutingProvider | None = None


def run_flood_aware_route(
    *,
    route_input: FloodRouteInput,
    settings: Settings,
    dependencies: FloodRouteDependencies,
) -> dict[str, Any]:
    request_id = uuid4().hex[:8]
    request_started = perf_counter()
    artifact_path = route_input.artifact_path or settings.default_artifact

    LOGGER.info(
        "route_request_started request_id=%s source=%s artifact_path=%s start=(%.6f,%.6f) end=(%.6f,%.6f)",
        request_id,
        route_input.source,
        artifact_path,
        route_input.start.lat,
        route_input.start.lon,
        route_input.end.lat,
        route_input.end.lon,
    )

    prepare_started = perf_counter()
    try:
        artifact_path = artifact_service.ensure_artifact_exists(
            artifact_path=artifact_path,
            source=route_input.source,
            ingest_fn=dependencies.ingest_fn,
            allow_request_ingestion=settings.allow_request_ingestion,
        )

        all_geometries = dependencies.load_geometries_fn(artifact_path)
        selected_geometries = polygon_selection_service.select_nearest_polygons_to_midpoint(
            all_geometries,
            start=route_input.start,
            end=route_input.end,
            limit=settings.max_avoid_polygons,
        )
    except Exception:
        total_ms = (perf_counter() - request_started) * 1000
        LOGGER.exception(
            "route_request_prepare_failed request_id=%s duration_ms=%.1f",
            request_id,
            total_ms,
        )
        raise

    prepare_ms = (perf_counter() - prepare_started) * 1000
    LOGGER.info(
        "route_request_prepared request_id=%s duration_ms=%.1f high_risk_total=%d selected_for_avoidance=%d",
        request_id,
        prepare_ms,
        len(all_geometries),
        len(selected_geometries),
    )

    routing_provider = dependencies.routing_provider or routing_service.get_routing_provider()
    build_avoid_fn = dependencies.build_avoid_fn or (
        lambda geometries: routing_service.build_avoid_polygons(
            geometries,
            simplify_tolerance_degrees=settings.simplify_tolerance_degrees,
        )
    )
    call_route_fn = dependencies.call_route_fn or routing_provider.route

    route_started = perf_counter()
    try:
        result = routing_service.compute_flood_aware_route(
            start=route_input.start,
            end=route_input.end,
            artifact_path=artifact_path,
            load_geometries_fn=lambda _: selected_geometries,
            build_avoid_fn=build_avoid_fn,
            fallback_radius_meters=settings.ors_fallback_radius_meters,
            call_route_fn=call_route_fn,
            routing_provider=routing_provider,
        )
    except Exception:
        route_ms = (perf_counter() - route_started) * 1000
        total_ms = (perf_counter() - request_started) * 1000
        LOGGER.exception(
            "route_request_failed request_id=%s route_ms=%.1f total_ms=%.1f",
            request_id,
            route_ms,
            total_ms,
        )
        raise

    _validate_route_response(result)

    route_ms = (perf_counter() - route_started) * 1000
    total_ms = (perf_counter() - request_started) * 1000
    LOGGER.info(
        "route_request_succeeded request_id=%s route_ms=%.1f total_ms=%.1f "
        "using_avoid_polygons=%s using_custom_radiuses=%s avoidance_polygon_count=%d",
        request_id,
        route_ms,
        total_ms,
        result.get("using_avoid_polygons"),
        result.get("using_custom_radiuses"),
        result.get("avoidance_polygon_count", 0),
    )
    return result


def _validate_route_response(result: dict[str, Any]) -> None:
    required_keys = {
        "artifact_path",
        "high_risk_polygon_count",
        "avoidance_polygon_count",
        "using_avoid_polygons",
        "using_custom_radiuses",
        "route",
    }
    missing = sorted(required_keys - set(result))
    if missing:
        raise HTTPException(status_code=502, detail=f"Invalid route response: missing keys {missing}")

    route = result.get("route")
    if not isinstance(route, dict) or route.get("type") != "FeatureCollection":
        raise HTTPException(status_code=502, detail="Invalid route response: expected GeoJSON FeatureCollection")

    features = route.get("features")
    if not isinstance(features, list) or not features:
        raise HTTPException(status_code=502, detail="Invalid route response: route has no features")

    has_linestring = False
    for feature in features:
        if not isinstance(feature, dict):
            raise HTTPException(status_code=502, detail="Invalid route response: route feature must be an object")
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        if geometry.get("type") != "LineString":
            continue
        coordinates = geometry.get("coordinates")
        if isinstance(coordinates, list) and coordinates:
            has_linestring = True
            break

    if not has_linestring:
        raise HTTPException(
            status_code=502,
            detail="Invalid route response: expected at least one LineString feature with coordinates",
        )
