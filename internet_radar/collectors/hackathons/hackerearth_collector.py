from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import HackerEarthCollector

Collector = architecture_collector(name="HackerEarth", category="hackathons", live_factory=HackerEarthCollector, topic="hackerearth challenges", score=60)
