from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import TLDRNewsletterCollector

Collector = architecture_collector(
    name="TLDR Newsletter",
    category="news",
    live_factory=TLDRNewsletterCollector,
    topic="tech newsletter signals",
    score=55,
)
