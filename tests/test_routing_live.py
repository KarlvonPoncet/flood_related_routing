from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from api import routing as routing_module


def _live_ors_enabled() -> bool:
    return os.getenv("RUN_LIVE_ORS_TESTS", "").lower() in {"1", "true", "yes"}


@pytest.mark.live_ors
@pytest.mark.skipif(
    not _live_ors_enabled(),
    reason="Set RUN_LIVE_ORS_TESTS=1 to enable tests that call OpenRouteService",
)
def test_route_gateway_calls_real_ors(tmp_path: Path) -> None:
    if not os.getenv("ORS_API_KEY"):
        pytest.skip("ORS_API_KEY is required for live ORS tests")

    artifact = tmp_path / "live.geojson"
    artifact.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")

    req = routing_module.RouteAvoidFloodsRequest(
        start=routing_module.Coordinate(lat=46.0569, lon=14.5058),
        end=routing_module.Coordinate(lat=45.8150, lon=15.9819),
        artifact_path=str(artifact),
    )

    payload = routing_module.route_avoid_flood_high_risk(req)

    assert payload["artifact_path"] == str(artifact)
    assert payload["high_risk_polygon_count"] == 0
    assert payload["using_avoid_polygons"] is False

    route = payload["route"]
    assert route["type"] == "FeatureCollection"
    features = route.get("features", [])
    assert isinstance(features, list)
    assert len(features) > 0

    summary = features[0].get("properties", {}).get("summary", {})
    assert float(summary.get("distance", 0)) > 0
    assert float(summary.get("duration", 0)) > 0
