from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Wayback Machine", category="search", topic="web archive changes", score=55)
