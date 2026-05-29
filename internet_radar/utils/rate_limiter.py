from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock


Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class SourceRateLimiter:
    def __init__(
        self,
        default_interval_seconds: float = 1.0,
        source_intervals: dict[str, float] | None = None,
        now: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
    ) -> None:
        self.default_interval_seconds = default_interval_seconds
        self.source_intervals = {_normalize(source): seconds for source, seconds in (source_intervals or {}).items()}
        self.now = now
        self.sleep = sleep
        self.last_access: dict[str, float] = {}
        self._lock = Lock()

    def wait(self, source: str) -> None:
        key = _normalize(source)
        while True:
            with self._lock:
                current = self.now()
                previous = self.last_access.get(key)
                interval = self.source_intervals.get(key, self.default_interval_seconds)
                wait_for = interval - (current - previous) if previous is not None else 0.0
                if wait_for <= 0:
                    self.last_access[key] = current
                    return
            self.sleep(wait_for)


def _normalize(source: str) -> str:
    return " ".join(source.lower().split())


DEFAULT_SOURCE_INTERVALS: dict[str, float] = {
    "github search": 2.0,
    "github trending": 5.0,
    "gitlab explore": 1.0,
    "mcp servers directory": 1.0,
    "pypi": 1.0,
    "npm registry": 1.0,
    "package velocity": 1.0,
    "crates.io": 1.0,
    "hacker news": 0.5,
    "hn algolia": 0.5,
    "reddit json": 2.0,
    "bluesky": 1.0,
    "mastodon": 1.0,
    "stack overflow": 1.0,
    "dev.to": 1.0,
    "hashnode": 2.0,
    "tech rss": 0.5,
    "company engineering blogs": 0.5,
    "conference rss": 0.5,
    "tldr newsletter": 2.0,
    "indie hackers": 2.0,
    "remoteok": 2.0,
    "the muse": 1.0,
    "yc jobs": 2.0,
    "arbeitnow": 1.0,
    "devpost": 2.0,
    "mlh": 2.0,
    "leetcode contests": 2.0,
    "codeforces": 1.0,
    "arxiv": 3.0,
    "openalex": 1.0,
    "hugging face models": 1.0,
    "hugging face papers": 1.0,
    "wikipedia pageviews": 0.5,
    "papers with code": 1.0,
    "coingecko": 3.0,
    "yahoo finance": 2.0,
    "opencollective": 2.0,
    "yc companies": 2.0,
    "sec edgar": 0.2,
    "itunes app store": 0.5,
    "google play": 5.0,
    "steam": 1.0,
    "duckduckgo": 5.0,
    "focused web crawler": 5.0,
    "google trends": 5.0,
    "wayback machine": 1.0,
    "libraries.io": 2.0,
    "product hunt": 2.0,
    "adzuna": 1.0,
    "hackerearth": 2.0,
    "semantic scholar": 1.0,
    "crunchbase": 2.0,
    "brave search": 1.0,
    "tavily": 1.0,
}

DEFAULT_RATE_LIMITER = SourceRateLimiter(default_interval_seconds=0.0, source_intervals=DEFAULT_SOURCE_INTERVALS)
