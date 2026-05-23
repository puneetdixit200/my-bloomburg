from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import SteamCollector

Collector = architecture_collector(name="Steam", category="app_stores", live_factory=SteamCollector, topic="steam app signals", score=60)
