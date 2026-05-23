from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import LobstersCollector

Collector = architecture_collector(name="Lobsters", category="news", live_factory=LobstersCollector, topic="lobsters stories", score=62)
