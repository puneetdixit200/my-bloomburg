from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import ArxivCollector

Collector = architecture_collector(name="arXiv", category="research", live_factory=ArxivCollector, topic="arxiv papers", score=77)
