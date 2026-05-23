from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import RSSCollector

Collector = architecture_collector(
    name="Tech RSS",
    category="news",
    live_factory=RSSCollector,
    topic="rss technology news",
    score=58,
)
