from __future__ import annotations

import json
from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.data.flood_api import GloFASRapidRiskAssessmentAdapter


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class GloFASRapidRiskAssessmentAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = GloFASRapidRiskAssessmentAdapter(
            base_url="https://example.test/api",
            api_key="secret",
        )
        self.since = datetime(2026, 4, 24, 8, 0, tzinfo=timezone.utc)

    @patch("app.data.flood_api.request.urlopen")
    def test_fetch_events_from_feature_collection(self, mock_urlopen) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": "evt-geojson-1",
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[10.0, 45.0], [11.0, 45.0], [11.0, 46.0], [10.0, 46.0], [10.0, 45.0]]],
                    },
                    "properties": {
                        "observation_time": "2026-04-24T09:00:00Z",
                        "severity": 0.8,
                        "confidence": 0.9,
                    },
                }
            ],
        }
        mock_urlopen.return_value = _FakeHTTPResponse(payload)

        events = self.adapter.fetch_events(bbox=(9.0, 44.0, 12.0, 47.0), since=self.since)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "glofas_rra")
        self.assertEqual(events[0]["event_id"], "evt-geojson-1")
        self.assertAlmostEqual(events[0]["severity"], 0.8)

    @patch("app.data.flood_api.request.urlopen")
    def test_fetch_events_from_results_payload(self, mock_urlopen) -> None:
        payload = {
            "results": [
                {
                    "event_id": "evt-res-1",
                    "bbox": [12.0, 50.0, 13.0, 51.0],
                    "timestamp": "2026-04-24T09:30:00Z",
                    "risk_score": 0.7,
                    "probability": 0.6,
                }
            ]
        }
        mock_urlopen.return_value = _FakeHTTPResponse(payload)

        events = self.adapter.fetch_events(bbox=(11.5, 49.8, 13.2, 51.2), since=self.since)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event_id"], "evt-res-1")
        self.assertAlmostEqual(events[0]["severity"], 0.7)
        self.assertAlmostEqual(events[0]["confidence"], 0.6)
        self.assertEqual(events[0]["geometry"]["type"], "Polygon")

    @patch("app.data.flood_api.request.urlopen")
    def test_health_ok(self, mock_urlopen) -> None:
        mock_urlopen.return_value = _FakeHTTPResponse({"status": "healthy"})
        status = self.adapter.health()
        self.assertTrue(status.ok)
        self.assertEqual(status.source, "glofas_rra")


if __name__ == "__main__":
    unittest.main()

