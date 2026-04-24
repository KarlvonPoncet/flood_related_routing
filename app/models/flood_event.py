from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _clamp_01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(slots=True)
class FloodEvent:
    event_id: str
    source: str
    observation_time: datetime
    ingested_at: datetime
    severity: float
    confidence: float
    geometry: dict[str, Any]
    properties: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.observation_time.tzinfo is None:
            self.observation_time = self.observation_time.replace(tzinfo=timezone.utc)
        if self.ingested_at.tzinfo is None:
            self.ingested_at = self.ingested_at.replace(tzinfo=timezone.utc)
        self.severity = _clamp_01(self.severity)
        self.confidence = _clamp_01(self.confidence)

    def data_age_minutes(self, at_time: datetime | None = None) -> int:
        now = at_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        delta = now - self.observation_time
        return max(0, int(delta.total_seconds() // 60))


@dataclass(slots=True)
class FloodTile:
    tile_id: str
    bbox: tuple[float, float, float, float]
    risk_value: float
    resolution_m: int
    valid_from: datetime
    valid_to: datetime

    def __post_init__(self) -> None:
        self.risk_value = _clamp_01(self.risk_value)


@dataclass(slots=True)
class RouteRiskSegment:
    segment_id: str
    route_id: str
    geometry: dict[str, Any]
    risk_score: float
    risk_reason: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.risk_score = _clamp_01(self.risk_score)


@dataclass(slots=True)
class RiskResult:
    risk_score: float
    event_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.risk_score = _clamp_01(self.risk_score)

