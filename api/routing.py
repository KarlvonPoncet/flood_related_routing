from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union

from api.ingestion import ingest_file


router = APIRouter()

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT = ROOT_DIR / "data/processed/live_flood.geojson"
ORS_DIRECTIONS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
MAX_AVOID_POLYGONS = 200
SIMPLIFY_TOLERANCE_DEGREES = 0.005


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)


class RouteAvoidFloodsRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    source: str = "default"
    artifact_path: str | None = None


def _load_high_risk_geometries(artifact_path: Path) -> list[Any]:
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

        if len(geometries) >= MAX_AVOID_POLYGONS:
            break

    return geometries


def _build_avoid_polygons(geometries: list[Any]) -> dict[str, Any] | None:
    if not geometries:
        return None

    merged = unary_union(geometries)

    if merged.is_empty:
        return None

    simplified = merged.simplify(SIMPLIFY_TOLERANCE_DEGREES, preserve_topology=True)
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


def _call_openrouteservice(*, start: Coordinate, end: Coordinate, avoid_polygons: dict[str, Any] | None) -> dict[str, Any]:
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing ORS_API_KEY environment variable")

    body: dict[str, Any] = {
        "coordinates": [
            [start.lon, start.lat],
            [end.lon, end.lat],
        ],
    }

    if avoid_polygons is not None:
        body["options"] = {"avoid_polygons": avoid_polygons}

    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        ORS_DIRECTIONS_URL,
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


@router.post("/route/avoid-flood-high-risk")
def route_avoid_flood_high_risk(req: RouteAvoidFloodsRequest) -> dict[str, Any]:
    artifact_path = Path(req.artifact_path) if req.artifact_path else DEFAULT_ARTIFACT

    if not artifact_path.exists():
        artifact_path = ingest_file(source=req.source, target=str(artifact_path))

    geometries = _load_high_risk_geometries(artifact_path)
    avoid_polygons = _build_avoid_polygons(geometries)
    ors_response = _call_openrouteservice(start=req.start, end=req.end, avoid_polygons=avoid_polygons)

    return {
        "artifact_path": str(artifact_path),
        "high_risk_polygon_count": len(geometries),
        "using_avoid_polygons": avoid_polygons is not None,
        "route": ors_response,
    }
