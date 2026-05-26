from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta
from typing import Any

from internet_radar.storage.models import HistoricalTrend, SignalRecord, SignalSnapshot


PREFERRED_HISTORY_METRICS = [
    "stars",
    "recent_downloads",
    "downloads",
    "pull_count",
    "views",
    "citations",
    "result_count",
    "participants",
    "current_participants",
    "amount",
    "score",
    "velocity",
]


def velocity_score(current: float, previous: float = 0.0) -> int:
    if current <= 0:
        return 0
    if previous <= 0:
        return min(int(current), 100)
    return max(0, min(int(((current - previous) / previous) * 100), 100))


def historical_trend_for_signal(
    signal: SignalRecord,
    snapshots: Sequence[SignalSnapshot],
    *,
    metric: str | None = None,
    now: object | None = None,
) -> HistoricalTrend:
    metric = metric or (snapshots[0].metric if snapshots else "score")
    ordered = sorted(snapshots, key=lambda snapshot: snapshot.observed_at)
    current_snapshot = ordered[-1] if ordered else None
    current_observed_at = _observed_at(signal, current_snapshot)
    current_value = _current_metric_value(signal, metric, current_snapshot)
    previous = _previous_snapshot(ordered, current_observed_at)
    value_3d = _baseline_value(ordered, current_observed_at, days=3)
    value_7d = _baseline_value(ordered, current_observed_at, days=7)
    delta_3d = _delta(current_value, value_3d)
    delta_7d = _delta(current_value, value_7d)
    return HistoricalTrend(
        signal_id=str(signal.id),
        topic=signal.topic,
        title=signal.title,
        source=signal.source,
        category=signal.category,
        metric=metric,
        current_value=_round_value(current_value),
        previous_value=_round_value(previous.value) if previous else None,
        value_3d_ago=_round_value(value_3d) if value_3d is not None else None,
        value_7d_ago=_round_value(value_7d) if value_7d is not None else None,
        delta_3d=_round_value(delta_3d) if delta_3d is not None else None,
        delta_7d=_round_value(delta_7d) if delta_7d is not None else None,
        acceleration_3d_per_day=_round_value(delta_3d / 3) if delta_3d is not None else None,
        acceleration_7d_per_day=_round_value(delta_7d / 7) if delta_7d is not None else None,
        direction=_direction(current_value, value_3d, previous.value if previous else None),
        velocity_score=velocity_score(current_value, value_3d if value_3d is not None else (previous.value if previous else 0)),
        confidence=_confidence(value_3d, value_7d, previous),
        observed_at=current_observed_at,
    )


def historical_trends_for_signals(
    signals: list[SignalRecord],
    store: Any,
    *,
    now: object | None = None,
    limit: int = 50,
) -> list[HistoricalTrend]:
    trends: list[HistoricalTrend] = []
    for signal in signals:
        trend = historical_trend_for_best_metric(signal, store, now=now)
        if trend:
            trends.append(trend)
    return sorted(trends, key=lambda trend: (trend.velocity_score, trend.confidence), reverse=True)[:limit]


def historical_trend_for_best_metric(
    signal: SignalRecord,
    store: Any,
    *,
    now: object | None = None,
) -> HistoricalTrend | None:
    for metric in _metric_candidates(signal):
        try:
            snapshots = store.metric_history(signal_id=str(signal.id), metric=metric)
        except AttributeError:
            return None
        if snapshots:
            return historical_trend_for_signal(signal, snapshots, metric=metric, now=now)
    return None


def apply_historical_velocity(signals: list[SignalRecord], trends: list[HistoricalTrend]) -> None:
    by_id = {trend.signal_id: trend for trend in trends}
    for signal in signals:
        trend = by_id.get(str(signal.id))
        if trend is None:
            continue
        signal.metadata["historical_metric"] = trend.metric
        signal.metadata["historical_velocity_score"] = trend.velocity_score
        signal.metadata["historical_direction"] = trend.direction
        if trend.acceleration_3d_per_day is not None:
            signal.velocity = float(trend.acceleration_3d_per_day)


def _metric_candidates(signal: SignalRecord) -> list[str]:
    metadata_metrics = [
        metric
        for metric in PREFERRED_HISTORY_METRICS
        if metric in {"score", "velocity"} or _is_number(signal.metadata.get(metric))
    ]
    extras = [
        str(key)
        for key, value in signal.metadata.items()
        if _is_number(value) and str(key) not in metadata_metrics
    ]
    return [*metadata_metrics, *extras]


def _observed_at(signal: SignalRecord, current_snapshot: SignalSnapshot | None):
    return current_snapshot.observed_at if current_snapshot else signal.observed_at


def _current_metric_value(signal: SignalRecord, metric: str, current_snapshot: SignalSnapshot | None) -> float:
    if metric == "score":
        return float(signal.score)
    if metric == "velocity":
        return float(signal.velocity)
    if _is_number(signal.metadata.get(metric)):
        return float(signal.metadata[metric])
    return float(current_snapshot.value) if current_snapshot else 0.0


def _previous_snapshot(snapshots: Sequence[SignalSnapshot], current_observed_at: object) -> SignalSnapshot | None:
    older = [snapshot for snapshot in snapshots if snapshot.observed_at < current_observed_at]
    return older[-1] if older else None


def _baseline_value(snapshots: Sequence[SignalSnapshot], current_observed_at: object, *, days: int) -> float | None:
    target = current_observed_at - timedelta(days=days)
    candidates = [snapshot for snapshot in snapshots if snapshot.observed_at <= target]
    if not candidates:
        return None
    return float(candidates[-1].value)


def _delta(current: float, previous: float | None) -> float | None:
    return current - previous if previous is not None else None


def _direction(current: float, value_3d: float | None, previous: float | None) -> str:
    baseline = value_3d if value_3d is not None else previous
    if baseline is None:
        return "new"
    if current > baseline:
        return "up"
    if current < baseline:
        return "down"
    return "flat"


def _confidence(value_3d: float | None, value_7d: float | None, previous: SignalSnapshot | None) -> int:
    if value_3d is not None and value_7d is not None:
        return 90
    if value_3d is not None:
        return 70
    if previous is not None:
        return 55
    return 35


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _round_value(value: float) -> float:
    return round(float(value), 3)
