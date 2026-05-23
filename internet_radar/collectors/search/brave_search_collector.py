from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import BraveSearchCollector

Collector = architecture_collector(name="Brave Search", category="search", live_factory=BraveSearchCollector, topic="brave search intelligence", score=58)
