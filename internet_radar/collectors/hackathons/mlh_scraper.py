from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import MLHCollector

Collector = architecture_collector(
    name="MLH",
    category="hackathons",
    live_factory=MLHCollector,
    topic="mlh hackathons",
    score=65,
)
