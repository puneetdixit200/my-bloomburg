from __future__ import annotations

import time
from collections.abc import Callable


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

    def wait(self, source: str) -> None:
        key = _normalize(source)
        current = self.now()
        previous = self.last_access.get(key)
        interval = self.source_intervals.get(key, self.default_interval_seconds)
        if previous is not None:
            wait_for = interval - (current - previous)
            if wait_for > 0:
                self.sleep(wait_for)
                current = self.now()
        self.last_access[key] = current


def _normalize(source: str) -> str:
    return " ".join(source.lower().split())
