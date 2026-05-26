from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class CollectorResult:
    name: str
    category: str
    signals: list[SignalRecord]
    status: str
    duration_seconds: float = 0.0


def collect_from_sources(collectors: Sequence[object], max_workers: int | None = None) -> list[CollectorResult]:
    if not collectors:
        return []
    workers = max_workers or min(8, len(collectors))
    if workers <= 1 or len(collectors) == 1:
        return [_collect_one(collector) for collector in collectors]

    indexed_results: list[tuple[int, CollectorResult]] = []
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="radar-collector") as executor:
        futures = {executor.submit(_collect_one, collector): index for index, collector in enumerate(collectors)}
        for future in as_completed(futures):
            indexed_results.append((futures[future], future.result()))

    return [result for _, result in sorted(indexed_results, key=lambda item: item[0])]


def _collect_one(collector: object) -> CollectorResult:
    name = str(getattr(collector, "name", collector.__class__.__name__))
    category = str(getattr(collector, "category", "unknown"))
    started = perf_counter()
    try:
        raw_signals = getattr(collector, "collect")()
        signals = _coerce_signals(raw_signals)
        return CollectorResult(
            name=name,
            category=category,
            signals=signals,
            status=_status_for_signals(signals),
            duration_seconds=round(perf_counter() - started, 3),
        )
    except Exception as exc:
        return CollectorResult(
            name=name,
            category=category,
            signals=[],
            status=f"error: {exc}",
            duration_seconds=round(perf_counter() - started, 3),
        )


def _coerce_signals(raw_signals: Any) -> list[SignalRecord]:
    if raw_signals is None:
        return []
    return [signal for signal in list(raw_signals) if isinstance(signal, SignalRecord)]


def _status_for_signals(signals: list[SignalRecord]) -> str:
    mode = "fallback" if signals and all(_is_fallback_signal(signal) for signal in signals) else "live"
    return f"{mode} ({len(signals)})"


def _is_fallback_signal(signal: SignalRecord) -> bool:
    return bool(
        signal.metadata.get("fallback")
        or signal.metadata.get("requires_api_key")
        or str(signal.id or "").startswith(("source-fallback:", "keyed-fallback:"))
    )
