from __future__ import annotations

from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass

from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class TrendCorrelation:
    topic: str
    score: int
    verdict: str
    sources: list[str]
    categories: list[str]
    signal_ids: list[str]


def correlate_trends(signals: list[SignalRecord], min_sources: int = 2) -> list[TrendCorrelation]:
    grouped: dict[str, list[SignalRecord]] = defaultdict(list)
    for signal in signals:
        grouped[_topic_key(signal.topic)].append(signal)

    correlations: list[TrendCorrelation] = []
    for topic, records in grouped.items():
        sources = _unique(signal.source for signal in records)
        if len(sources) < min_sources:
            continue
        categories = _unique(signal.category for signal in records)
        score = _correlation_score(records, sources, categories)
        correlations.append(
            TrendCorrelation(
                topic=topic,
                score=score,
                verdict=_verdict(score, sources, categories),
                sources=sources,
                categories=categories,
                signal_ids=[str(signal.id) for signal in records],
            )
        )

    return sorted(correlations, key=lambda item: (item.score, len(item.sources), len(item.categories)), reverse=True)


def _correlation_score(records: list[SignalRecord], sources: list[str], categories: list[str]) -> int:
    average_score = sum(signal.score for signal in records) / len(records)
    average_velocity = sum(float(signal.velocity) for signal in records) / len(records)
    score = average_score * 0.55
    score += min(len(sources) * 13, 35)
    score += min(len(categories) * 8, 25)
    score += min(average_velocity / 10, 10)
    return round(min(score, 100))


def _verdict(score: int, sources: list[str], categories: list[str]) -> str:
    if len(sources) >= 5 or len(categories) >= 5:
        return "ACT NOW"
    if len(sources) >= 3 or len(categories) >= 3 or score >= 80:
        return "STRONG"
    return "WEAK SIGNAL"


def _topic_key(topic: str) -> str:
    return " ".join(topic.strip().lower().split())


def _unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            unique_values.append(text)
            seen.add(text)
    return unique_values
