from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import SECEdgarCollector

Collector = architecture_collector(name="SEC EDGAR", category="finance", live_factory=SECEdgarCollector, topic="sec filings", score=65)
