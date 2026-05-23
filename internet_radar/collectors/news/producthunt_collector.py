from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Product Hunt", category="news", topic="product launches", score=55)
