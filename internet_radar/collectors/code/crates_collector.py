from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="crates.io", category="code", topic="rust package velocity", score=58)
