from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Crunchbase", category="finance", topic="funding rounds", score=64)
