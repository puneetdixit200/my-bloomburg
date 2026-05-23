from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import PyPICollector

Collector = architecture_collector(
    name="PyPI",
    category="code",
    live_factory=PyPICollector,
    topic="python package velocity",
    score=64,
)
