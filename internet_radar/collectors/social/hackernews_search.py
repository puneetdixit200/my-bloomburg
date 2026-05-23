from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import HNAlgoliaCollector

Collector = architecture_collector(
    name="HN Algolia",
    category="social",
    live_factory=HNAlgoliaCollector,
    topic="hacker news search",
    score=74,
)
