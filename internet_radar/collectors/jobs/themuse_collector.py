from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import TheMuseCollector

Collector = architecture_collector(name="The Muse", category="jobs", live_factory=TheMuseCollector, topic="muse jobs", score=62)
