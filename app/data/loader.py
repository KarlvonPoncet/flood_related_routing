from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.models import FloodEvent
from app.utils.geo import BBox, bbox_intersects, geometry_bbox


def _parse_datetime(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _clamp_01(value: Any, default: float = 0.0) -> float:
    try:
        f_value = float(value)
    except (TypeError, ValueError):
        f_value = default
    return max(0.0, min(1.0, f_value))


@dataclass(slots=True)
class FloodDataLoader:
    source_priorities: dict[str, int] = field(
        default_factory=lambda: {
            "copernicus_ems": 1,
            "glofas_rra": 2,
            "sentinel_derived": 3,
            "historical": 4,
            "mock": 99,
        }
    )

    def normalize(self, raw_event: dict[str, Any] | FloodEvent) -> FloodEvent:
        if isinstance(raw_event, FloodEvent):
            return raw_event

        properties = raw_event.get("properties", {})
        event_id = str(raw_event.get("event_id") or raw_event.get("id") or "")
        if not event_id:
            geometry_fragment = json.dumps(raw_event.get("geometry", {}), sort_keys=True)
            event_id = f"evt-{hashlib.sha1(geometry_fragment.encode('utf-8')).hexdigest()[:12]}"

        source = str(raw_event.get("source") or properties.get("source") or "unknown")
        geometry = raw_event.get("geometry") or {}
        severity = _clamp_01(raw_event.get("severity", properties.get("severity", 0.5)), 0.5)
        confidence = _clamp_01(raw_event.get("confidence", properties.get("confidence", 0.7)), 0.7)
        observation_time = _parse_datetime(
            raw_event.get("observation_time")
            or raw_event.get("observationTime")
            or properties.get("observation_time")
            or properties.get("timestamp")
        )

        return FloodEvent(
            event_id=event_id,
            source=source,
            observation_time=observation_time,
            ingested_at=datetime.now(timezone.utc),
            severity=severity,
            confidence=confidence,
            geometry=geometry,
            properties=dict(properties),
        )

    def validate(self, event: FloodEvent) -> bool:
        if not event.event_id or not event.source:
            return False
        if not (0.0 <= event.severity <= 1.0 and 0.0 <= event.confidence <= 1.0):
            return False
        if event.geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            return False
        try:
            geometry_bbox(event.geometry)
        except (ValueError, TypeError, KeyError, IndexError):
            return False
        return True

    def merge(self, events: list[FloodEvent]) -> list[FloodEvent]:
        deduped: dict[str, FloodEvent] = {}
        for event in events:
            key = self._dedupe_key(event)
            existing = deduped.get(key)
            if existing is None or self._is_preferred(event, existing):
                deduped[key] = event
        return list(deduped.values())

    def _dedupe_key(self, event: FloodEvent) -> str:
        bucket = event.observation_time.replace(minute=0, second=0, microsecond=0).isoformat()
        geom_hash = hashlib.sha1(
            json.dumps(event.geometry, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return f"{event.event_id}|{geom_hash}|{bucket}"

    def _is_preferred(self, candidate: FloodEvent, current: FloodEvent) -> bool:
        p_candidate = self.source_priorities.get(candidate.source, 999)
        p_current = self.source_priorities.get(current.source, 999)
        if p_candidate != p_current:
            return p_candidate < p_current
        return candidate.observation_time > current.observation_time


@dataclass(slots=True)
class InMemoryFloodStore:
    _events: list[FloodEvent] = field(default_factory=list)
    _bbox_index: list[tuple[BBox, FloodEvent]] = field(default_factory=list)

    def upsert_events(self, events: list[FloodEvent]) -> None:
        self._events = list(events)
        self._bbox_index = [(geometry_bbox(event.geometry), event) for event in self._events]

    def query_all(self) -> list[FloodEvent]:
        return list(self._events)

    def query_bbox(self, bbox: BBox) -> list[FloodEvent]:
        return [event for event_bbox, event in self._bbox_index if bbox_intersects(event_bbox, bbox)]

    def query_active(self, at_time: datetime, max_age_hours: int = 48) -> list[FloodEvent]:
        max_age_minutes = max_age_hours * 60
        return [event for event in self._events if event.data_age_minutes(at_time) <= max_age_minutes]
