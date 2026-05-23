from __future__ import annotations

from dataclasses import dataclass

from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class SourceAgreement:
    topic: str
    sources: list[str]
    source_count: int
    known_source_count: int
    multiplier: float
    score: int
    verdict: str


def cross_source_multiplier(source_count: int) -> float:
    if source_count >= 5:
        return 1.3
    if source_count >= 3:
        return 1.15
    return 1.0


def apply_cross_source_multiplier(base_score: int | float, source_count: int) -> int:
    return min(round(float(base_score) * cross_source_multiplier(source_count)), 100)


def build_source_agreements(signals: list[SignalRecord], known_source_count: int = 8) -> list[SourceAgreement]:
    grouped: dict[str, list[SignalRecord]] = {}
    display_topics: dict[str, str] = {}
    for signal in signals:
        key = _topic_key(signal.topic)
        grouped.setdefault(key, []).append(signal)
        display_topics.setdefault(key, signal.topic.strip().lower())

    agreements: list[SourceAgreement] = []
    for key, records in grouped.items():
        sources: list[str] = []
        for signal in records:
            if signal.source not in sources:
                sources.append(signal.source)
        source_count = len(sources)
        base_score = max(signal.score for signal in records)
        score = apply_cross_source_multiplier(base_score, source_count)
        agreements.append(
            SourceAgreement(
                topic=display_topics[key],
                sources=sources,
                source_count=source_count,
                known_source_count=known_source_count,
                multiplier=cross_source_multiplier(source_count),
                score=score,
                verdict=_verdict(source_count, known_source_count),
            )
        )

    return sorted(agreements, key=lambda item: (item.score, item.source_count, item.topic), reverse=True)


def _topic_key(topic: str) -> str:
    return " ".join(topic.lower().strip().split())


def _verdict(source_count: int, known_source_count: int) -> str:
    if known_source_count and source_count >= known_source_count:
        return "ACT NOW"
    if source_count >= 3:
        return "STRONG"
    if source_count >= 2:
        return "WEAK SIGNAL"
    return "SINGLE SOURCE - WATCH"
