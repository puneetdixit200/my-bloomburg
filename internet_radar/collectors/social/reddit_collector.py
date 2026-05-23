from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import RedditJSONCollector

Collector = architecture_collector(name="Reddit JSON", category="social", live_factory=RedditJSONCollector, topic="reddit developer discussion", score=71)
