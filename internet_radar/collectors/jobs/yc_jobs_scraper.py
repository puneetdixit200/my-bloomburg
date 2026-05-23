from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import YCJobsCollector

Collector = architecture_collector(
    name="YC Jobs",
    category="jobs",
    live_factory=YCJobsCollector,
    topic="yc startup jobs",
    score=60,
)
