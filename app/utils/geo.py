from __future__ import annotations

from math import hypot
from typing import Iterable

Coordinate = tuple[float, float]  # (lon, lat)
BBox = tuple[float, float, float, float]


def geometry_bbox(geometry: dict) -> BBox:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        points = [p for ring in coords for p in ring]
    elif gtype == "MultiPolygon":
        points = [p for polygon in coords for ring in polygon for p in ring]
    else:
        raise ValueError(f"Unsupported geometry type: {gtype}")
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def bbox_intersects(a: BBox, b: BBox) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def polyline_bbox(polyline_lonlat: list[Coordinate]) -> BBox:
    xs = [p[0] for p in polyline_lonlat]
    ys = [p[1] for p in polyline_lonlat]
    return (min(xs), min(ys), max(xs), max(ys))


def _point_in_ring(point: Coordinate, ring: list[Coordinate]) -> bool:
    x, y = point
    inside = False
    n = len(ring)
    if n < 3:
        return False
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_intersection = (x2 - x1) * (y - y1) / ((y2 - y1) or 1e-12) + x1
            if x < x_intersection:
                inside = not inside
    return inside


def _point_in_polygon(point: Coordinate, polygon: list[list[Coordinate]]) -> bool:
    if not polygon:
        return False
    outer = polygon[0]
    holes = polygon[1:]
    if not _point_in_ring(point, outer):
        return False
    for hole in holes:
        if _point_in_ring(point, hole):
            return False
    return True


def point_in_geometry(point: Coordinate, geometry: dict) -> bool:
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if gtype == "Polygon":
        polygon = [[(float(p[0]), float(p[1])) for p in ring] for ring in coords]
        return _point_in_polygon(point, polygon)
    if gtype == "MultiPolygon":
        for polygon in coords:
            parsed = [[(float(p[0]), float(p[1])) for p in ring] for ring in polygon]
            if _point_in_polygon(point, parsed):
                return True
        return False
    raise ValueError(f"Unsupported geometry type: {gtype}")


def line_length(line: list[Coordinate]) -> float:
    if len(line) < 2:
        return 0.0
    total = 0.0
    for idx in range(len(line) - 1):
        x1, y1 = line[idx]
        x2, y2 = line[idx + 1]
        total += hypot(x2 - x1, y2 - y1)
    return total


def interpolate_segment(a: Coordinate, b: Coordinate, t: float) -> Coordinate:
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def line_coverage_in_geometry(
    line: list[Coordinate],
    geometry: dict,
    samples_per_segment: int = 12,
) -> float:
    if len(line) < 2:
        return 0.0
    inside = 0
    total = 0
    for idx in range(len(line) - 1):
        a = line[idx]
        b = line[idx + 1]
        for sample in range(samples_per_segment + 1):
            t = sample / float(samples_per_segment)
            point = interpolate_segment(a, b, t)
            inside += 1 if point_in_geometry(point, geometry) else 0
            total += 1
    return (inside / total) if total else 0.0


def latlon_to_lonlat(points: Iterable[tuple[float, float]]) -> list[Coordinate]:
    return [(float(lon), float(lat)) for lat, lon in points]

