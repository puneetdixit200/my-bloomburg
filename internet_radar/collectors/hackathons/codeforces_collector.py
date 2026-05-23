from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import CodeforcesCollector

Collector = architecture_collector(name="Codeforces", category="hackathons", live_factory=CodeforcesCollector, topic="codeforces contests", score=70)
