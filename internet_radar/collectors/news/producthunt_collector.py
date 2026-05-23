from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import ProductHuntCollector

Collector = architecture_collector(name="Product Hunt", category="news", live_factory=ProductHuntCollector, topic="product launches", score=55)
