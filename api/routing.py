from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.config import get_settings
from api.ingestion import ingest_file
from api.services import flood_route_workflow, path_policy_service, routing_service


router = APIRouter()


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RouteAvoidFloodsRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    source: str = "default"
    artifact_path: str | None = None


class RouteAvoidFloodsResponse(BaseModel):
    artifact_path: str
    high_risk_polygon_count: int
    avoidance_polygon_count: int
    using_avoid_polygons: bool
    using_custom_radiuses: bool
    route: dict[str, Any]
    warning: str | None = None


def _load_high_risk_geometries(artifact_path: Path) -> list[Any]:
    return routing_service.load_high_risk_geometries(artifact_path)


def _build_avoid_polygons(geometries: list[Any]) -> dict[str, Any] | None:
    settings = get_settings()
    return routing_service.build_avoid_polygons(
        geometries,
        simplify_tolerance_degrees=settings.simplify_tolerance_degrees,
    )


def _get_routing_provider() -> routing_service.RoutingProvider:
    return routing_service.get_routing_provider()


def _call_routing_provider(
    *,
    start: Coordinate,
    end: Coordinate,
    avoid_polygons: dict[str, Any] | None,
    radiuses: list[float] | None = None,
) -> dict[str, Any]:
    return _get_routing_provider().route(
        start=start,
        end=end,
        avoid_polygons=avoid_polygons,
        radiuses=radiuses,
    )


@router.post("/route/avoid-flood-high-risk", response_model=RouteAvoidFloodsResponse)
def route_avoid_flood_high_risk(req: RouteAvoidFloodsRequest) -> dict[str, Any]:
    settings = get_settings()
    artifact_path = (
        path_policy_service.resolve_artifact_path(req.artifact_path, settings=settings)
        if req.artifact_path
        else None
    )
    route_input = flood_route_workflow.FloodRouteInput(
        start=req.start,
        end=req.end,
        source=req.source,
        artifact_path=artifact_path,
    )
    dependencies = flood_route_workflow.FloodRouteDependencies(
        ingest_fn=ingest_file,
        load_geometries_fn=_load_high_risk_geometries,
        build_avoid_fn=_build_avoid_polygons,
        call_route_fn=_call_routing_provider,
        routing_provider=_get_routing_provider(),
    )
    return flood_route_workflow.run_flood_aware_route(
        route_input=route_input,
        settings=settings,
        dependencies=dependencies,
    )
