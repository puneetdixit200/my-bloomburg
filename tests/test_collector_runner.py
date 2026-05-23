from __future__ import annotations

import threading

from internet_radar.storage.models import SignalRecord


def test_collector_runner_runs_sources_in_parallel_and_preserves_order():
    from internet_radar.collectors.runner import collect_from_sources

    lock = threading.Lock()
    all_started = threading.Event()
    started = 0

    class WaitingCollector:
        category = "code"

        def __init__(self, name: str) -> None:
            self.name = name

        def collect(self):
            nonlocal started
            with lock:
                started += 1
                if started == 2:
                    all_started.set()
            assert all_started.wait(0.5)
            return [
                SignalRecord(
                    id=f"{self.name}:1",
                    topic="browser agents",
                    title=f"{self.name} signal",
                    source=self.name,
                    category="code",
                    score=70,
                )
            ]

    results = collect_from_sources([WaitingCollector("first"), WaitingCollector("second")], max_workers=2)

    assert [result.name for result in results] == ["first", "second"]
    assert [result.status for result in results] == ["ok (1)", "ok (1)"]
    assert [result.signals[0].source for result in results] == ["first", "second"]


def test_collector_runner_reports_errors_without_stopping_other_sources():
    from internet_radar.collectors.runner import collect_from_sources

    class GoodCollector:
        name = "Good"
        category = "news"

        def collect(self):
            return [
                SignalRecord(
                    id="good:1",
                    topic="streamlit",
                    title="Streamlit signal",
                    source=self.name,
                    category="news",
                    score=70,
                )
            ]

    class BadCollector:
        name = "Bad"
        category = "news"

        def collect(self):
            raise RuntimeError("temporary API outage")

    results = collect_from_sources([GoodCollector(), BadCollector()], max_workers=2)

    assert results[0].status == "ok (1)"
    assert results[1].signals == []
    assert results[1].status == "error: temporary API outage"
