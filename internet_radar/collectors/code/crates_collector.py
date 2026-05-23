from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import CratesIOCollector

Collector = architecture_collector(
    name="crates.io",
    category="code",
    live_factory=CratesIOCollector,
    topic="rust package velocity",
    score=58,
)
