from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import DevpostCollector

Collector = architecture_collector(
    name="Devpost",
    category="hackathons",
    live_factory=DevpostCollector,
    topic="devpost hackathons",
    score=70,
)
