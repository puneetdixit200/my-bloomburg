from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import GitHubSearchCollector

Collector = architecture_collector(name="GitHub Trending", category="code", live_factory=GitHubSearchCollector, topic="github trending", score=78)
