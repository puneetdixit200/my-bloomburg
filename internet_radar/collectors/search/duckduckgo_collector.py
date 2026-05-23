from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import DuckDuckGoCollector

Collector = architecture_collector(name="DuckDuckGo", category="search", live_factory=DuckDuckGoCollector, topic="search intelligence", score=67)
