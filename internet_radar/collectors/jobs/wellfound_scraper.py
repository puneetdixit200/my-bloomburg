from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Wellfound", category="jobs", topic="wellfound startup jobs", score=55)
