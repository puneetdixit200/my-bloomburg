from __future__ import annotations

from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class TrendPrediction:
    topic: str
    phase: str
    mainstream_months: int
    best_time_to_learn: str
    best_time_to_build: str
    best_time_to_invest: str
    confidence: int
    triggers: list[str]
    source_count: int
    route: LLMChoice


def predict_trend(
    topic: str,
    signals: list[SignalRecord],
    router: LLMRouter | None = None,
) -> TrendPrediction:
    router = router or LLMRouter()
    matching = [signal for signal in signals if _topic_key(signal.topic) == _topic_key(topic)]
    if not matching:
        matching = [signal for signal in signals if _topic_key(topic) in _topic_key(signal.topic)]
    route = router.route("trend_predict", _content_length(topic, matching))
    sources = _unique(signal.source for signal in matching)
    categories = _unique(signal.category for signal in matching)
    avg_score = sum(signal.score for signal in matching) / max(len(matching), 1)
    avg_velocity = sum(float(signal.velocity) for signal in matching) / max(len(matching), 1)
    confidence = round(min(avg_score * 0.6 + len(sources) * 10 + len(categories) * 5 + avg_velocity / 5, 100))
    phase = _phase(len(sources), len(categories), avg_velocity, confidence)
    return TrendPrediction(
        topic=_topic_key(topic),
        phase=phase,
        mainstream_months=_mainstream_months(phase, len(sources)),
        best_time_to_learn="now" if phase in {"emerging", "accelerating"} else "selectively",
        best_time_to_build="now" if phase == "accelerating" else "prototype",
        best_time_to_invest="after customer validation" if phase in {"emerging", "accelerating"} else "wait",
        confidence=confidence,
        triggers=_triggers(matching, sources),
        source_count=len(sources),
        route=route,
    )


def predict_trends(
    signals: list[SignalRecord],
    router: LLMRouter | None = None,
    limit: int = 10,
) -> list[TrendPrediction]:
    router = router or LLMRouter()
    grouped: dict[str, list[SignalRecord]] = defaultdict(list)
    for signal in signals:
        grouped[_topic_key(signal.topic)].append(signal)
    predictions = [
        predict_trend(topic, topic_signals, router=router)
        for topic, topic_signals in grouped.items()
        if len(_unique(signal.source for signal in topic_signals)) >= 2
    ]
    return sorted(predictions, key=lambda item: (item.confidence, item.source_count), reverse=True)[:limit]


def _phase(source_count: int, category_count: int, avg_velocity: float, confidence: int) -> str:
    if source_count >= 4 and category_count >= 3 and (avg_velocity >= 40 or confidence >= 85):
        return "accelerating"
    if source_count >= 2:
        return "emerging"
    if confidence >= 70:
        return "watch"
    return "single-source"


def _mainstream_months(phase: str, source_count: int) -> int:
    if phase == "accelerating":
        return 6
    if phase == "emerging":
        return 9 if source_count >= 3 else 12
    return 18


def _triggers(signals: list[SignalRecord], sources: list[str]) -> list[str]:
    triggers: list[str] = []
    if any(signal.category == "research" for signal in signals):
        triggers.append("research velocity")
    if any(signal.category == "finance" for signal in signals):
        triggers.append("funding validation")
    if any(signal.category == "jobs" for signal in signals):
        triggers.append("job demand")
    if len(sources) >= 3:
        triggers.append("cross-source confirmation")
    return triggers or ["more source confirmation"]


def _content_length(topic: str, signals: list[SignalRecord]) -> int:
    return len(topic) + sum(len(signal.title) + len(signal.summary) for signal in signals)


def _topic_key(topic: str) -> str:
    return " ".join(topic.strip().lower().split())


def _unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            unique_values.append(text)
            seen.add(text)
    return unique_values
