from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from api.config import Settings, get_settings
from api.osm_graph_ingestion import ingest_osm_graph


class _FakeGraph:
    def __init__(self, node_count: int = 3, edge_count: int = 2):
        self.nodes = list(range(node_count))
        self.edges = list(range(edge_count))


class _FakeAdapter:
    name = "fake-osm"
    version = "1.0"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def graph_from_place(self, place: str, *, network_type: str, simplify: bool) -> _FakeGraph:
        self.calls.append(
            {
                "method": "graph_from_place",
                "place": place,
                "network_type": network_type,
                "simplify": simplify,
            }
        )
        return _FakeGraph()

    def graph_from_bbox(
        self,
        *,
        north: float,
        south: float,
        east: float,
        west: float,
        network_type: str,
        simplify: bool,
    ) -> _FakeGraph:
        self.calls.append(
            {
                "method": "graph_from_bbox",
                "north": north,
                "south": south,
                "east": east,
                "west": west,
                "network_type": network_type,
                "simplify": simplify,
            }
        )
        return _FakeGraph()

    def save_graphml(self, graph: _FakeGraph, path: Path) -> None:
        del graph
        path.write_text("<graphml />", encoding="utf-8")


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    base = get_settings()
    values = {
        field: getattr(base, field)
        for field in Settings.__dataclass_fields__
    }
    values.update(
        {
            "custom_routing_graph_path": tmp_path / "custom-routing.graphml",
            "custom_routing_graph_metadata_path": tmp_path / "custom-routing.metadata.json",
            "custom_routing_osm_place": None,
            "custom_routing_osm_network_type": "drive",
            "custom_routing_simplify_graph": True,
            "eu_min_lon": 13.0,
            "eu_max_lon": 17.0,
            "eu_min_lat": 45.0,
            "eu_max_lat": 47.0,
        }
    )
    values.update(overrides)
    return Settings(**values)


def test_ingest_osm_graph_downloads_bbox_and_writes_metadata(tmp_path: Path) -> None:
    adapter = _FakeAdapter()
    settings = _settings(tmp_path)

    result = ingest_osm_graph(settings=settings, adapter=adapter)

    assert result.graph_path == tmp_path / "custom-routing.graphml"
    assert result.metadata_path == tmp_path / "custom-routing.metadata.json"
    assert result.node_count == 3
    assert result.edge_count == 2
    assert adapter.calls == [
        {
            "method": "graph_from_bbox",
            "north": 47.0,
            "south": 45.0,
            "east": 17.0,
            "west": 13.0,
            "network_type": "drive",
            "simplify": True,
        }
    ]

    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["source"] == "openstreetmap"
    assert metadata["source_area"]["type"] == "bbox"
    assert metadata["node_count"] == 3
    assert metadata["edge_count"] == 2
    assert result.graph_path.read_text(encoding="utf-8") == "<graphml />"


def test_ingest_osm_graph_prefers_configured_place(tmp_path: Path) -> None:
    adapter = _FakeAdapter()
    settings = _settings(
        tmp_path,
        custom_routing_osm_place="Slovenia",
        custom_routing_osm_network_type="bike",
        custom_routing_simplify_graph=False,
    )

    result = ingest_osm_graph(settings=settings, adapter=adapter)

    assert adapter.calls == [
        {
            "method": "graph_from_place",
            "place": "Slovenia",
            "network_type": "bike",
            "simplify": False,
        }
    ]
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    assert metadata["source_area"] == {"type": "place", "value": "Slovenia"}
    assert metadata["network_type"] == "bike"
    assert metadata["simplified"] is False


def test_ingest_osm_graph_rejects_empty_graph(tmp_path: Path) -> None:
    class _EmptyAdapter(_FakeAdapter):
        def graph_from_bbox(
            self,
            *,
            north: float,
            south: float,
            east: float,
            west: float,
            network_type: str,
            simplify: bool,
        ) -> _FakeGraph:
            del north, south, east, west, network_type, simplify
            return _FakeGraph(node_count=0, edge_count=0)

    with pytest.raises(RuntimeError, match="OpenStreetMap graph is empty"):
        ingest_osm_graph(settings=_settings(tmp_path), adapter=_EmptyAdapter())
