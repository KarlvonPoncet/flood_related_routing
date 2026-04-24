from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.data.flood_api import MockFloodAdapter
from app.services.shipment_service import ShipmentService


def _polygon(min_lon: float, min_lat: float, max_lon: float, max_lat: float) -> dict:
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [min_lon, min_lat],
                [max_lon, min_lat],
                [max_lon, max_lat],
                [min_lon, max_lat],
                [min_lon, min_lat],
            ]
        ],
    }


class ShipmentServiceDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.route = [(0.0, 0.0), (0.0, 2.0)]
        self.now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)

    def test_keep_route_when_no_events(self) -> None:
        service = ShipmentService(source_adapter=MockFloodAdapter(events=[]))
        result = service.evaluate_route(route_id="r1", polyline=self.route, at_time=self.now)
        self.assertEqual(result["decision"], "keep_route")
        self.assertEqual(result["risk_summary"]["max_risk"], 0.0)

    def test_warn_for_partial_overlap(self) -> None:
        events = [
            {
                "event_id": "warn-evt",
                "source": "mock",
                "observation_time": self.now.isoformat(),
                "severity": 0.5,
                "confidence": 0.9,
                "geometry": _polygon(0.8, -0.2, 1.2, 0.2),
                "properties": {},
            }
        ]
        service = ShipmentService(source_adapter=MockFloodAdapter(events=events))
        result = service.evaluate_route(route_id="r2", polyline=self.route, at_time=self.now)
        self.assertEqual(result["decision"], "warn")
        self.assertGreaterEqual(result["risk_summary"]["max_risk"], 0.35)
        self.assertLess(result["risk_summary"]["max_risk"], 0.6)

    def test_reroute_for_high_risk_overlap(self) -> None:
        events = [
            {
                "event_id": "reroute-evt",
                "source": "mock",
                "observation_time": self.now.isoformat(),
                "severity": 1.0,
                "confidence": 0.95,
                "geometry": _polygon(-0.5, -0.5, 2.5, 0.5),
                "properties": {},
            }
        ]
        service = ShipmentService(source_adapter=MockFloodAdapter(events=events))
        result = service.evaluate_route(route_id="r3", polyline=self.route, at_time=self.now)
        self.assertEqual(result["decision"], "reroute")
        self.assertGreater(result["risk_summary"]["max_risk"], 0.6)


if __name__ == "__main__":
    unittest.main()

