from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from shapely.geometry import GeometryCollection, mapping, shape
from shapely.ops import unary_union


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
