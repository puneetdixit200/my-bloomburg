from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import WikipediaPageviewsCollector

Collector = architecture_collector(name="Wikipedia Pageviews", category="research", live_factory=WikipediaPageviewsCollector, topic="wikipedia pageviews", score=62)
