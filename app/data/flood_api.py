from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import parse, request
from urllib.error import HTTPError, URLError
from typing import Any

from app.models import FloodEvent, SourceStatus
from app.utils.geo import BBox, bbox_intersects, geometry_bbox


class FloodSourceAdapter(ABC):
    @abstractmethod
    def fetch_events(
        self, bbox: BBox | None = None, since: datetime | None = None
    ) -> list[dict[str, Any] | FloodEvent]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> SourceStatus:
        raise NotImplementedError


class MockFloodAdapter(FloodSourceAdapter):
    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events = events or self._default_events()

    def fetch_events(
        self, bbox: BBox | None = None, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        since = since or datetime.now(timezone.utc) - timedelta(hours=24)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        filtered: list[dict[str, Any]] = []
        for raw in self._events:
            obs = datetime.fromisoformat(raw["observation_time"].replace("Z", "+00:00"))
            if obs < since:
                continue
            if bbox is not None:
                if not bbox_intersects(bbox, geometry_bbox(raw["geometry"])):
                    continue
            filtered.append(raw)
        return filtered

    def health(self) -> SourceStatus:
        return SourceStatus(source="mock", ok=True, message=f"{len(self._events)} events loaded")

    @staticmethod
    def _default_events() -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return [
            {
                "event_id": "mock-berlin-1",
                "source": "mock",
                "observation_time": now.isoformat(),
                "severity": 0.6,
                "confidence": 0.8,
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[13.2, 52.4], [13.6, 52.4], [13.6, 52.7], [13.2, 52.7], [13.2, 52.4]]],
                },
                "properties": {"name": "Mock Flood Berlin"},
            }
        ]


class CopernicusEMSAdapter(FloodSourceAdapter):
    def __init__(self, geojson_path: str) -> None:
        self.geojson_path = Path(geojson_path)

    def fetch_events(
        self, bbox: BBox | None = None, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        if not self.geojson_path.exists():
            return []
        since = since or datetime.now(timezone.utc) - timedelta(days=7)
        if since.tzinfo is None:
            since = since.replace(tzinfo=timezone.utc)

        payload = json.loads(self.geojson_path.read_text(encoding="utf-8"))
        features = payload.get("features", [])
        events: list[dict[str, Any]] = []

        for feature in features:
            properties = feature.get("properties", {})
            obs_raw = properties.get("observation_time") or properties.get("timestamp")
            obs_dt = datetime.fromisoformat(str(obs_raw).replace("Z", "+00:00")) if obs_raw else datetime.now(timezone.utc)
            if obs_dt < since:
                continue
            geometry = feature.get("geometry", {})
            if bbox is not None and not bbox_intersects(bbox, geometry_bbox(geometry)):
                continue
            events.append(
                {
                    "event_id": str(feature.get("id") or properties.get("id") or ""),
                    "source": "copernicus_ems",
                    "observation_time": obs_dt.isoformat(),
                    "severity": properties.get("severity", 0.7),
                    "confidence": properties.get("confidence", 0.8),
                    "geometry": geometry,
                    "properties": properties,
                }
            )
        return events

    def health(self) -> SourceStatus:
        if not self.geojson_path.exists():
            return SourceStatus(source="copernicus_ems", ok=False, message="GeoJSON file not found")
        return SourceStatus(source="copernicus_ems", ok=True, message="GeoJSON source reachable")


class GloFASRapidRiskAssessmentAdapter(FloodSourceAdapter):
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout_seconds: int = 20,
        path: str = "/rapid-risk-assessment",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.path = path
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def fetch_events(
        self, bbox: BBox | None = None, since: datetime | None = None
    ) -> list[dict[str, Any]]:
        since = since or datetime.now(timezone.utc) - timedelta(hours=24)
        since = self._as_utc(since)
        query: dict[str, str] = {"since": since.isoformat()}
        if bbox is not None:
            query["bbox"] = ",".join(str(v) for v in bbox)
        url = f"{self.base_url}{self.path}?{parse.urlencode(query)}"
        payload = self._request_json(url)
        return self._payload_to_events(payload, bbox=bbox, since=since)

    def health(self) -> SourceStatus:
        url = f"{self.base_url}/health"
        try:
            payload = self._request_json(url)
        except (URLError, HTTPError, TimeoutError, ValueError) as exc:
            return SourceStatus(source="glofas_rra", ok=False, message=f"Health check failed: {exc}")
        message = "ok"
        if isinstance(payload, dict):
            message = str(payload.get("status") or payload.get("message") or "ok")
        return SourceStatus(source="glofas_rra", ok=True, message=message)

    def _request_json(self, url: str) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = request.Request(url=url, headers=headers, method="GET")
        with request.urlopen(req, timeout=self.timeout_seconds) as response:
            body = response.read().decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("Unexpected API payload")
        return data

    def _payload_to_events(
        self,
        payload: dict[str, Any],
        bbox: BBox | None,
        since: datetime,
    ) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []

        if payload.get("type") == "FeatureCollection":
            features = list(payload.get("features", []))
        elif isinstance(payload.get("results"), list):
            for idx, item in enumerate(payload["results"]):
                if not isinstance(item, dict):
                    continue
                geometry = item.get("geometry")
                if geometry is None and item.get("bbox"):
                    geometry = self._bbox_to_polygon(item["bbox"])
                if geometry is None:
                    continue
                features.append(
                    {
                        "id": item.get("event_id") or item.get("id") or f"glofas-rra-{idx}",
                        "type": "Feature",
                        "geometry": geometry,
                        "properties": item,
                    }
                )
        else:
            return []

        events: list[dict[str, Any]] = []
        for feature in features:
            properties = feature.get("properties", {})
            geometry = feature.get("geometry") or {}
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                continue

            obs = self._extract_observation_time(properties)
            if obs < since:
                continue
            if bbox is not None and not bbox_intersects(bbox, geometry_bbox(geometry)):
                continue

            events.append(
                {
                    "event_id": str(feature.get("id") or properties.get("event_id") or ""),
                    "source": "glofas_rra",
                    "observation_time": obs.isoformat(),
                    "severity": self._extract_severity(properties),
                    "confidence": self._extract_confidence(properties),
                    "geometry": geometry,
                    "properties": dict(properties),
                }
            )
        return events

    @staticmethod
    def _extract_observation_time(properties: dict[str, Any]) -> datetime:
        raw = (
            properties.get("observation_time")
            or properties.get("timestamp")
            or properties.get("valid_time")
            or datetime.now(timezone.utc).isoformat()
        )
        if isinstance(raw, datetime):
            return GloFASRapidRiskAssessmentAdapter._as_utc(raw)
        return GloFASRapidRiskAssessmentAdapter._as_utc(
            datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        )

    @staticmethod
    def _extract_severity(properties: dict[str, Any]) -> float:
        for key in ("severity", "risk_score", "risk", "alert_level"):
            if key in properties:
                try:
                    value = float(properties[key])
                    return max(0.0, min(1.0, value))
                except (TypeError, ValueError):
                    continue
        return 0.5

    @staticmethod
    def _extract_confidence(properties: dict[str, Any]) -> float:
        for key in ("confidence", "certainty", "probability"):
            if key in properties:
                try:
                    value = float(properties[key])
                    return max(0.0, min(1.0, value))
                except (TypeError, ValueError):
                    continue
        return 0.7

    @staticmethod
    def _bbox_to_polygon(raw_bbox: Any) -> dict[str, Any] | None:
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
            return None
        min_lon, min_lat, max_lon, max_lat = [float(v) for v in raw_bbox]
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

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
