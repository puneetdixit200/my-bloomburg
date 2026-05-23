from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import MastodonCollector

Collector = architecture_collector(
    name="Mastodon",
    category="social",
    live_factory=MastodonCollector,
    topic="mastodon developer signals",
    score=58,
)
