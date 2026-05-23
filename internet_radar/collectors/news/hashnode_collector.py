from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import HashnodeCollector

Collector = architecture_collector(
    name="Hashnode",
    category="news",
    live_factory=HashnodeCollector,
    topic="hashnode developer articles",
    score=55,
)
