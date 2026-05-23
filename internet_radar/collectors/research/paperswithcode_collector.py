from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import PapersWithCodeCollector

Collector = architecture_collector(name="Papers With Code", category="research", live_factory=PapersWithCodeCollector, topic="papers with code", score=72)
