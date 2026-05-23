from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import WaybackCollector

Collector = architecture_collector(
    name="Wayback Machine",
    category="search",
    live_factory=WaybackCollector,
    topic="web archive changes",
    score=55,
)
