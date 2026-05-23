from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import TavilyCollector

Collector = architecture_collector(name="Tavily", category="search", live_factory=TavilyCollector, topic="ai search intelligence", score=58)
