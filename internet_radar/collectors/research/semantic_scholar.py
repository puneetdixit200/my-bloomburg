from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import SemanticScholarCollector

Collector = architecture_collector(name="Semantic Scholar", category="research", live_factory=SemanticScholarCollector, topic="semantic scholar papers", score=62)
