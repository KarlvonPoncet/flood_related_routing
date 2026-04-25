from __future__ import annotations

from typing import Any, Protocol

from shapely.geometry import Point


class CoordinateLike(Protocol):
    lat: float
    lon: float


def midpoint(start: CoordinateLike, end: CoordinateLike) -> Point:
    return Point((start.lon + end.lon) / 2.0, (start.lat + end.lat) / 2.0)


def select_nearest_polygons_to_midpoint(
    geometries: list[Any],
    *,
    start: CoordinateLike,
    end: CoordinateLike,
    limit: int,
) -> list[Any]:
    if limit <= 0:
        return []

    if len(geometries) <= limit:
        return geometries

    center = midpoint(start, end)
    indexed = list(enumerate(geometries))
    indexed.sort(key=lambda pair: (pair[1].distance(center), pair[0]))
    return [geom for _, geom in indexed[:limit]]
