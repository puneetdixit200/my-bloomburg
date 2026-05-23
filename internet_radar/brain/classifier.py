from __future__ import annotations

from dataclasses import dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.signals.keyword_extractor import extract_entities, extract_keywords
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class SignalClassification:
    signal_id: str
    topic: str
    category: str
    sentiment: str
    confidence: int
    keywords: list[str]
    entities: list[str]
    route: LLMChoice


def classify_signal(
    signal: SignalRecord,
    router: LLMRouter | None = None,
    allow_network: bool = False,
) -> SignalClassification:
    router = router or LLMRouter()
    text = " ".join(part for part in [signal.topic, signal.title, signal.summary] if part)
    route = router.route("classify", len(text))
    result = router.classify_signal(text, allow_network=allow_network)
    return SignalClassification(
        signal_id=str(signal.id),
        topic=str(result["topic"]),
        category=signal.category,
        sentiment=str(result["sentiment"]),
        confidence=int(result["confidence"]),
        keywords=extract_keywords(text, limit=8),
        entities=extract_entities(text, limit=8),
        route=route,
    )


def classify_signals(
    signals: list[SignalRecord],
    router: LLMRouter | None = None,
    limit: int = 20,
    allow_network: bool = False,
) -> list[SignalClassification]:
    router = router or LLMRouter()
    return [
        classify_signal(signal, router=router, allow_network=allow_network)
        for signal in sorted(signals, key=lambda item: item.score, reverse=True)[:limit]
    ]
