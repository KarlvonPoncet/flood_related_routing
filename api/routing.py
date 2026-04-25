from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.config import get_settings
from api.ingestion import ingest_file
from api.services import artifact_service, routing_service


router = APIRouter()

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
    return routing_service.load_high_risk_geometries(
        artifact_path,
        max_avoid_polygons=MAX_AVOID_POLYGONS,
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


@router.post("/route/avoid-flood-high-risk")
def route_avoid_flood_high_risk(req: RouteAvoidFloodsRequest) -> dict[str, Any]:
    artifact_path = Path(req.artifact_path) if req.artifact_path else DEFAULT_ARTIFACT

    artifact_path = artifact_service.ensure_artifact_exists(
        artifact_path=artifact_path,
        source=req.source,
        ingest_fn=ingest_file,
    )

    return routing_service.compute_flood_aware_route(
        start=req.start,
        end=req.end,
        artifact_path=artifact_path,
        load_geometries_fn=_load_high_risk_geometries,
        build_avoid_fn=_build_avoid_polygons,
        call_ors_fn=_call_openrouteservice,
        fallback_radius_meters=get_settings().ors_fallback_radius_meters,
        area_error_fn=_is_ors_avoid_polygon_area_error,
        unroutable_error_fn=_is_ors_unroutable_point_error,
    )
