from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Any

from app.data.flood_api import FloodSourceAdapter
from app.data.loader import FloodDataLoader, InMemoryFloodStore
from app.logic.risk_calculator import FloodRiskCalculator
from app.utils.config import DataConfig, RiskThresholds
from app.utils.geo import BBox, polyline_bbox


@dataclass(slots=True)
class ShipmentService:
    source_adapter: FloodSourceAdapter
    loader: FloodDataLoader = field(default_factory=FloodDataLoader)
    store: InMemoryFloodStore = field(default_factory=InMemoryFloodStore)
    thresholds: RiskThresholds = field(default_factory=RiskThresholds)
    data_config: DataConfig = field(default_factory=DataConfig)
    risk_calculator: FloodRiskCalculator = field(init=False)

    def __post_init__(self) -> None:
        self.risk_calculator = FloodRiskCalculator(
            event_provider=lambda at_time: self.store.query_active(
                at_time, max_age_hours=self.data_config.event_ttl_hours
            ),
            data_config=self.data_config,
        )

    def refresh_data(self, bbox: BBox | None = None, since: datetime | None = None) -> int:
        since = since or datetime.now(timezone.utc) - timedelta(hours=self.data_config.event_ttl_hours)
        raw_events = self.source_adapter.fetch_events(bbox=bbox, since=since)
        normalized = [self.loader.normalize(event) for event in raw_events]
        valid_events = [event for event in normalized if self.loader.validate(event)]
        merged = self.loader.merge(valid_events)
        self.store.upsert_events(merged)
        return len(merged)

    def evaluate_route(
        self,
        route_id: str,
        polyline: list[tuple[float, float]],
        at_time: datetime | None = None,
    ) -> dict[str, Any]:
        at_time = at_time or datetime.now(timezone.utc)
        if at_time.tzinfo is None:
            at_time = at_time.replace(tzinfo=timezone.utc)

        route_bbox = polyline_bbox([(lon, lat) for lat, lon in polyline]) if len(polyline) >= 2 else None
        self.refresh_data(bbox=route_bbox, since=at_time - timedelta(hours=self.data_config.event_ttl_hours))

        segments = self.risk_calculator.risk_for_polyline(polyline=polyline, at_time=at_time, route_id=route_id)
        max_risk = max((segment.risk_score for segment in segments), default=0.0)
        avg_risk = fmean([segment.risk_score for segment in segments]) if segments else 0.0

        if max_risk > self.thresholds.reroute_above:
            decision = "reroute"
        elif max_risk >= self.thresholds.keep_below:
            decision = "warn"
        else:
            decision = "keep_route"

        all_events = self.store.query_active(at_time, max_age_hours=self.data_config.event_ttl_hours)
        explainability = self._build_explainability(all_events, at_time)
        affected_segments = sum(1 for segment in segments if segment.risk_score >= self.thresholds.keep_below)

        return {
            "decision": decision,
            "risk_summary": {
                "max_risk": round(max_risk, 3),
                "avg_risk": round(avg_risk, 3),
                "affected_segments": affected_segments,
                "total_segments": len(segments),
            },
            "explainability": explainability,
            "segments": [
                {
                    "segment_id": segment.segment_id,
                    "risk_score": round(segment.risk_score, 3),
                    "risk_reason": segment.risk_reason,
                }
                for segment in segments
            ],
        }

    @staticmethod
    def _build_explainability(events: list, at_time: datetime) -> dict[str, Any]:
        if not events:
            return {
                "top_events": [],
                "data_age_minutes": None,
                "event_count": 0,
            }
        sorted_events = sorted(events, key=lambda event: event.severity, reverse=True)
        data_ages = [event.data_age_minutes(at_time) for event in events]
        return {
            "top_events": [event.event_id for event in sorted_events[:3]],
            "data_age_minutes": {"min": min(data_ages), "max": max(data_ages)},
            "event_count": len(events),
        }
