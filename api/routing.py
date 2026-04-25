from __future__ import annotations

import logging
from time import perf_counter
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.config import get_settings
from api.ingestion import ingest_file
from api.services import artifact_service, polygon_selection_service, routing_service


router = APIRouter()
LOGGER = logging.getLogger(__name__)

SETTINGS = get_settings()
DEFAULT_ARTIFACT = SETTINGS.default_artifact
ORS_DIRECTIONS_URL = SETTINGS.ors_directions_url
MAX_AVOID_POLYGONS = SETTINGS.max_avoid_polygons
SIMPLIFY_TOLERANCE_DEGREES = SETTINGS.simplify_tolerance_degrees


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RouteAvoidFloodsRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    source: str = "default"
    artifact_path: str | None = None


def _load_high_risk_geometries(artifact_path: Path) -> list[Any]:
    return routing_service.load_high_risk_geometries(artifact_path)


def _select_nearest_avoid_geometries(
    geometries: list[Any],
    *,
    start: Coordinate,
    end: Coordinate,
) -> list[Any]:
    return polygon_selection_service.select_nearest_polygons_to_midpoint(
        geometries,
        start=start,
        end=end,
        limit=MAX_AVOID_POLYGONS,
    )


def _build_avoid_polygons(geometries: list[Any]) -> dict[str, Any] | None:
    return routing_service.build_avoid_polygons(
        geometries,
        simplify_tolerance_degrees=SIMPLIFY_TOLERANCE_DEGREES,
    )


def _call_openrouteservice(
    *,
    start: Coordinate,
    end: Coordinate,
    avoid_polygons: dict[str, Any] | None,
    radiuses: list[float] | None = None,
) -> dict[str, Any]:
    return routing_service.call_openrouteservice(
        start=start,
        end=end,
        avoid_polygons=avoid_polygons,
        radiuses=radiuses,
    )


def _is_ors_avoid_polygon_area_error(exc: HTTPException) -> bool:
    return routing_service.is_ors_avoid_polygon_area_error(exc)


def _is_ors_unroutable_point_error(exc: HTTPException) -> bool:
    return routing_service.is_ors_unroutable_point_error(exc)


def _is_ors_distance_limit_error(exc: HTTPException) -> bool:
    return routing_service.is_ors_distance_limit_error(exc)


@router.post("/route/avoid-flood-high-risk")
def route_avoid_flood_high_risk(req: RouteAvoidFloodsRequest) -> dict[str, Any]:
    request_id = uuid4().hex[:8]
    request_started = perf_counter()
    artifact_path = Path(req.artifact_path) if req.artifact_path else DEFAULT_ARTIFACT

    LOGGER.info(
        "route_request_started request_id=%s source=%s artifact_path=%s start=(%.6f,%.6f) end=(%.6f,%.6f)",
        request_id,
        req.source,
        artifact_path,
        req.start.lat,
        req.start.lon,
        req.end.lat,
        req.end.lon,
    )

    prepare_started = perf_counter()
    try:
        artifact_path = artifact_service.ensure_artifact_exists(
            artifact_path=artifact_path,
            source=req.source,
            ingest_fn=ingest_file,
        )

        all_geometries = _load_high_risk_geometries(artifact_path)
        selected_geometries = _select_nearest_avoid_geometries(
            all_geometries,
            start=req.start,
            end=req.end,
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

    route_started = perf_counter()
    try:
        result = routing_service.compute_flood_aware_route(
            start=req.start,
            end=req.end,
            artifact_path=artifact_path,
            load_geometries_fn=lambda _: selected_geometries,
            build_avoid_fn=_build_avoid_polygons,
            call_ors_fn=_call_openrouteservice,
            fallback_radius_meters=get_settings().ors_fallback_radius_meters,
            area_error_fn=_is_ors_avoid_polygon_area_error,
            unroutable_error_fn=_is_ors_unroutable_point_error,
            distance_error_fn=_is_ors_distance_limit_error,
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
