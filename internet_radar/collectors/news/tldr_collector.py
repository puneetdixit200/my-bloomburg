from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="TLDR Newsletter", category="news", topic="tech newsletter signals", score=55)
