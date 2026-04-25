from __future__ import annotations

from shapely.geometry import Point

from api.services import polygon_selection_service as selection


class _Coord:
    def __init__(self, lat: float, lon: float) -> None:
        self.lat = lat
        self.lon = lon


def test_select_nearest_polygons_returns_all_when_under_limit() -> None:
    geometries = [Point(0, 0).buffer(0.1), Point(1, 1).buffer(0.1)]
    out = selection.select_nearest_polygons_to_midpoint(
        geometries,
        start=_Coord(lat=0.0, lon=0.0),
        end=_Coord(lat=2.0, lon=2.0),
        limit=10,
    )
    assert out == geometries


def test_select_nearest_polygons_to_midpoint_respects_limit() -> None:
    geometries = [Point(20, 0).buffer(0.1), Point(10, 0).buffer(0.1), Point(1, 0).buffer(0.1)]
    out = selection.select_nearest_polygons_to_midpoint(
        geometries,
        start=_Coord(lat=0.0, lon=0.0),
        end=_Coord(lat=0.0, lon=0.0),
        limit=2,
    )

    centers = sorted(round(g.centroid.x) for g in out)
    assert centers == [1, 10]
