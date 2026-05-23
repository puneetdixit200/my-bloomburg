from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import PackageCollector

Collector = architecture_collector(name="PyPI", category="code", live_factory=PackageCollector, topic="python package velocity", score=64)
