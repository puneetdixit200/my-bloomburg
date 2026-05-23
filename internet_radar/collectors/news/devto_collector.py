from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import DevToCollector

Collector = architecture_collector(name="Dev.to", category="news", live_factory=DevToCollector, topic="developer articles", score=68)
