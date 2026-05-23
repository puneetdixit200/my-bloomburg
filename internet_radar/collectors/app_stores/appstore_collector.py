from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import ITunesCollector

Collector = architecture_collector(name="iTunes App Store", category="app_stores", live_factory=ITunesCollector, topic="app store pain", score=66)
