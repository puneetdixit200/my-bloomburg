from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import GoogleTrendsCollector

Collector = architecture_collector(
    name="Google Trends",
    category="search",
    live_factory=GoogleTrendsCollector,
    topic="rising search queries",
    score=68,
)
