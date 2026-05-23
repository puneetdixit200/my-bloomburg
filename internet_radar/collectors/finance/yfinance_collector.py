from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import YahooFinanceCollector

Collector = architecture_collector(
    name="Yahoo Finance",
    category="finance",
    live_factory=YahooFinanceCollector,
    topic="stock trends",
    score=60,
)
