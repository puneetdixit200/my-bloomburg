from __future__ import annotations

from internet_radar.collectors.adapters import architecture_collector
from internet_radar.collectors.live import LeetCodeContestsCollector

Collector = architecture_collector(
    name="LeetCode Contests",
    category="hackathons",
    live_factory=LeetCodeContestsCollector,
    topic="leetcode contests",
    score=60,
)
