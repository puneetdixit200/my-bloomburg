from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import ArbeitnowCollector

Collector = architecture_collector(name="Arbeitnow", category="jobs", live_factory=ArbeitnowCollector, topic="arbeitnow jobs", score=62)
