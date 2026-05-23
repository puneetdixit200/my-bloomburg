from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector

Collector = architecture_collector(name="Nitter", category="social", topic="twitter trend fallback", score=52)
