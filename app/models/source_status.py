from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class SourceStatus:
    source: str
    ok: bool
    message: str = ""
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

