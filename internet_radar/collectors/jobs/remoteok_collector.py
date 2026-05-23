from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import RemoteOKCollector

Collector = architecture_collector(name="RemoteOK", category="jobs", live_factory=RemoteOKCollector, topic="remote jobs", score=79)
