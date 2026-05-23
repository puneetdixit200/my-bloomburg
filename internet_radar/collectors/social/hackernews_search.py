from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import HackerNewsCollector

Collector = architecture_collector(name="Hacker News", category="social", live_factory=HackerNewsCollector, topic="hacker news search", score=74)
