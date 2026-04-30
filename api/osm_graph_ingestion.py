from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from api.config import Settings, get_settings


class OsmGraphAdapter(Protocol):
    name: str
    version: str

    def graph_from_place(self, place: str, *, network_type: str, simplify: bool) -> Any:
        ...

    def graph_from_bbox(
        self,
        *,
        north: float,
        south: float,
        east: float,
        west: float,
        network_type: str,
        simplify: bool,
    ) -> Any:
        ...

    def save_graphml(self, graph: Any, path: Path) -> None:
        ...


@dataclass(frozen=True)
class OsmGraphIngestionResult:
    graph_path: Path
    metadata_path: Path
    node_count: int
    edge_count: int


class OsmnxGraphAdapter:
    name = "osmnx"

    def __init__(self) -> None:
        try:
            import osmnx as ox
        except ImportError as exc:
            raise RuntimeError(
                "Missing OSM graph ingestion dependency. Install runtime dependencies with: "
                "python -m pip install -r requirements.txt"
            ) from exc
        self._ox = ox
        self.version = getattr(ox, "__version__", "unknown")

    def graph_from_place(self, place: str, *, network_type: str, simplify: bool) -> Any:
        return self._ox.graph_from_place(place, network_type=network_type, simplify=simplify)

    def graph_from_bbox(
        self,
        *,
        north: float,
        south: float,
        east: float,
        west: float,
        network_type: str,
        simplify: bool,
    ) -> Any:
        try:
            return self._ox.graph_from_bbox(
                north,
                south,
                east,
                west,
                network_type=network_type,
                simplify=simplify,
            )
        except TypeError:
            return self._ox.graph_from_bbox(
                bbox=(west, south, east, north),
                network_type=network_type,
                simplify=simplify,
            )

    def save_graphml(self, graph: Any, path: Path) -> None:
        self._ox.save_graphml(graph, filepath=path)


def ingest_osm_graph(
    *,
    settings: Settings | None = None,
    adapter: OsmGraphAdapter | None = None,
) -> OsmGraphIngestionResult:
    settings = settings or get_settings()
    adapter = adapter or OsmnxGraphAdapter()

    if settings.custom_routing_osm_place:
        graph = adapter.graph_from_place(
            settings.custom_routing_osm_place,
            network_type=settings.custom_routing_osm_network_type,
            simplify=settings.custom_routing_simplify_graph,
        )
        source_area: dict[str, Any] = {
            "type": "place",
            "value": settings.custom_routing_osm_place,
        }
    else:
        graph = adapter.graph_from_bbox(
            north=settings.eu_max_lat,
            south=settings.eu_min_lat,
            east=settings.eu_max_lon,
            west=settings.eu_min_lon,
            network_type=settings.custom_routing_osm_network_type,
            simplify=settings.custom_routing_simplify_graph,
        )
        source_area = {
            "type": "bbox",
            "north": settings.eu_max_lat,
            "south": settings.eu_min_lat,
            "east": settings.eu_max_lon,
            "west": settings.eu_min_lon,
        }

    node_count = _graph_node_count(graph)
    edge_count = _graph_edge_count(graph)
    if node_count == 0 or edge_count == 0:
        raise RuntimeError("Downloaded OpenStreetMap graph is empty.")

    graph_path = settings.custom_routing_graph_path
    metadata_path = settings.custom_routing_graph_metadata_path
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    adapter.save_graphml(graph, graph_path)
    metadata = {
        "source": "openstreetmap",
        "adapter": adapter.name,
        "adapter_version": adapter.version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "graph_path": str(graph_path),
        "network_type": settings.custom_routing_osm_network_type,
        "simplified": settings.custom_routing_simplify_graph,
        "source_area": source_area,
        "node_count": node_count,
        "edge_count": edge_count,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return OsmGraphIngestionResult(
        graph_path=graph_path,
        metadata_path=metadata_path,
        node_count=node_count,
        edge_count=edge_count,
    )


def _graph_node_count(graph: Any) -> int:
    nodes = getattr(graph, "nodes", None)
    if nodes is None:
        return 0
    try:
        return len(nodes)
    except TypeError:
        return len(list(nodes()))


def _graph_edge_count(graph: Any) -> int:
    edges = getattr(graph, "edges", None)
    if edges is None:
        return 0
    try:
        return len(edges)
    except TypeError:
        return len(list(edges()))


if __name__ == "__main__":
    result = ingest_osm_graph()
    print(f"Wrote OSM routing graph to {result.graph_path}")
    print(f"Wrote OSM routing graph metadata to {result.metadata_path}")
