from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RiskWeights:
    severity: float = 0.5
    coverage: float = 0.3
    recency: float = 0.2


@dataclass(frozen=True, slots=True)
class RiskThresholds:
    keep_below: float = 0.35
    reroute_above: float = 0.6


@dataclass(frozen=True, slots=True)
class DataConfig:
    recency_window_minutes: int = 360
    event_ttl_hours: int = 48

