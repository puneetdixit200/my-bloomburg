from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="YC Jobs", category="jobs", topic="yc startup jobs", score=60)
