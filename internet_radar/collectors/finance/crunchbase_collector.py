from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import CrunchbaseCollector

Collector = architecture_collector(name="Crunchbase", category="finance", live_factory=CrunchbaseCollector, topic="funding rounds", score=64)
