from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import BlueskyCollector

Collector = architecture_collector(
    name="Bluesky",
    category="social",
    live_factory=BlueskyCollector,
    topic="bluesky early adopter signals",
    score=58,
)
