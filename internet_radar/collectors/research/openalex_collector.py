from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import OpenAlexCollector

Collector = architecture_collector(name="OpenAlex", category="research", live_factory=OpenAlexCollector, topic="openalex research", score=72)
