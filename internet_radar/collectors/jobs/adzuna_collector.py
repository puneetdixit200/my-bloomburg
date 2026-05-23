from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import AdzunaCollector

Collector = architecture_collector(name="Adzuna", category="jobs", live_factory=AdzunaCollector, topic="adzuna jobs", score=57)
