from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import LibrariesIOCollector

Collector = architecture_collector(name="Libraries.io", category="code", live_factory=LibrariesIOCollector, topic="cross language dependencies", score=58)
