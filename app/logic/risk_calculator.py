from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from app.models import FloodEvent, RiskResult, RouteRiskSegment
from app.utils.config import DataConfig, RiskWeights
from app.utils.geo import (
    bbox_intersects,
    geometry_bbox,
    latlon_to_lonlat,
    line_coverage_in_geometry,
    polyline_bbox,
    point_in_geometry,
)


@dataclass(slots=True)
class FloodRiskCalculator:
    event_provider: Callable[[datetime], list[FloodEvent]]
    weights: RiskWeights = field(default_factory=RiskWeights)
    data_config: DataConfig = field(default_factory=DataConfig)

    def risk_for_point(self, lat: float, lon: float, at_time: datetime | None = None) -> RiskResult:
        at_time = self._as_utc(at_time)
        events = self.event_provider(at_time)
        score = 0.0
        reasons: list[str] = []
        event_ids: list[str] = []
        for event in events:
            if not point_in_geometry((lon, lat), event.geometry):
                continue
            event_score = self._event_score(event, coverage=1.0, at_time=at_time)
            if event_score > score:
                score = event_score
            event_ids.append(event.event_id)
            reasons.append(f"{event.source} severity={event.severity:.2f} confidence={event.confidence:.2f}")
        return RiskResult(risk_score=score, event_ids=event_ids, reasons=reasons)

    def risk_for_polyline(
        self,
        polyline: list[tuple[float, float]],
        at_time: datetime | None = None,
        route_id: str = "route",
    ) -> list[RouteRiskSegment]:
        at_time = self._as_utc(at_time)
        if len(polyline) < 2:
            return []

        line = latlon_to_lonlat(polyline)
        events = self.event_provider(at_time)
        segments: list[RouteRiskSegment] = []
        for idx in range(len(line) - 1):
            seg_line = [line[idx], line[idx + 1]]
            seg_bbox = polyline_bbox(seg_line)
            seg_risk = 0.0
            seg_reasons: list[str] = []
            for event in events:
                event_bbox = geometry_bbox(event.geometry)
                if not bbox_intersects(seg_bbox, event_bbox):
                    continue
                coverage = line_coverage_in_geometry(seg_line, event.geometry)
                if coverage <= 0:
                    continue
                score = self._event_score(event, coverage=coverage, at_time=at_time)
                if score > seg_risk:
                    seg_risk = score
                seg_reasons.append(
                    f"{event.event_id}:{event.source} cov={coverage:.2f} sev={event.severity:.2f} conf={event.confidence:.2f}"
                )
            segments.append(
                RouteRiskSegment(
                    segment_id=f"{route_id}-seg-{idx}",
                    route_id=route_id,
                    geometry={"type": "LineString", "coordinates": [[*seg_line[0]], [*seg_line[1]]]},
                    risk_score=seg_risk,
                    risk_reason=seg_reasons,
                )
            )
        return segments

    def _event_score(self, event: FloodEvent, coverage: float, at_time: datetime) -> float:
        recency = self._recency_factor(event, at_time)
        return (
            self.weights.severity * event.severity
            + self.weights.coverage * max(0.0, min(1.0, coverage))
            + self.weights.recency * recency
        )

    def _recency_factor(self, event: FloodEvent, at_time: datetime) -> float:
        age = event.data_age_minutes(at_time)
        return max(0.0, 1.0 - age / float(self.data_config.recency_window_minutes))

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

