from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import GooglePlayCollector

Collector = architecture_collector(
    name="Google Play",
    category="app_stores",
    live_factory=GooglePlayCollector,
    topic="google play reviews",
    score=58,
)
