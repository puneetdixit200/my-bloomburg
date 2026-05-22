from __future__ import annotations

import re

from internet_radar.storage.models import SignalRecord


def deduplicate_signals(signals: list[SignalRecord]) -> list[SignalRecord]:
    best_by_key: dict[str, SignalRecord] = {}
    for signal in signals:
        key = _key(signal)
        current = best_by_key.get(key)
        if current is None or (signal.score, signal.observed_at) > (current.score, current.observed_at):
            best_by_key[key] = signal
    return sorted(best_by_key.values(), key=lambda item: (item.score, item.observed_at), reverse=True)


def _key(signal: SignalRecord) -> str:
    text = f"{signal.topic} {signal.title}".lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()
