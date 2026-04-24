from __future__ import annotations

from datetime import datetime, timezone
import unittest

from app.data.loader import FloodDataLoader


class FloodDataLoaderTests(unittest.TestCase):
    def test_merge_prefers_high_priority_source(self) -> None:
        loader = FloodDataLoader(source_priorities={"copernicus_ems": 1, "mock": 99})
        geometry = {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0], [0.0, 0.0]]],
        }
        older = loader.normalize(
            {
                "event_id": "evt-1",
                "source": "mock",
                "observation_time": "2026-04-24T10:00:00Z",
                "severity": 0.3,
                "confidence": 0.8,
                "geometry": geometry,
            }
        )
        preferred = loader.normalize(
            {
                "event_id": "evt-1",
                "source": "copernicus_ems",
                "observation_time": "2026-04-24T10:20:00Z",
                "severity": 0.7,
                "confidence": 0.8,
                "geometry": geometry,
            }
        )
        merged = loader.merge([older, preferred])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source, "copernicus_ems")

    def test_validate_rejects_invalid_geometry(self) -> None:
        loader = FloodDataLoader()
        event = loader.normalize(
            {
                "event_id": "evt-invalid",
                "source": "mock",
                "observation_time": datetime.now(timezone.utc).isoformat(),
                "severity": 0.5,
                "confidence": 0.5,
                "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [1.0, 1.0]]},
            }
        )
        self.assertFalse(loader.validate(event))


if __name__ == "__main__":
    unittest.main()

