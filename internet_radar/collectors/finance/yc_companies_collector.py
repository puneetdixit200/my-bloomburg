from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import YCCompaniesCollector

Collector = architecture_collector(name="YC Companies", category="finance", live_factory=YCCompaniesCollector, topic="yc companies", score=73)
