from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def signals_above_threshold(signals: list[SignalRecord], threshold: int = 80) -> list[SignalRecord]:
    return [signal for signal in signals if signal.score >= threshold]
