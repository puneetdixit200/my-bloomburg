from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from internet_radar.storage.models import SignalRecord


PAIN_TERMS = {
    "abandoned",
    "broken",
    "bug",
    "complaint",
    "crash",
    "decline",
    "doesn't",
    "expensive",
    "frustrating",
    "hate",
    "manual",
    "missing",
    "pain",
    "slow",
    "too much",
    "worse",
}
POSITIVE_TERMS = {"love", "useful", "great", "fast", "excellent", "improving", "growth", "popular"}


@dataclass(frozen=True)
class SentimentResult:
    signal_id: str
    label: str
    sentiment_score: int
    frustration_score: int
    pain_terms: list[str]


def analyze_sentiment(signal: SignalRecord) -> SentimentResult:
    text = _signal_text(signal)
    pain_terms = [term for term in sorted(PAIN_TERMS) if term in text]
    positive_hits = sum(1 for term in POSITIVE_TERMS if term in text)
    rating = signal.metadata.get("rating")
    rating_penalty = 20 if isinstance(rating, (int, float)) and 0 < rating < 3 else 0

    frustration = min(len(pain_terms) * 18 + rating_penalty + _source_pain_bonus(signal), 100)
    sentiment_score = max(0, min(100, 50 + positive_hits * 15 - frustration // 2))
    if frustration >= 45:
        label = "negative"
    elif positive_hits > 0 and frustration < 30:
        label = "positive"
    else:
        label = "neutral"

    return SentimentResult(
        signal_id=str(signal.id),
        label=label,
        sentiment_score=sentiment_score,
        frustration_score=frustration,
        pain_terms=pain_terms,
    )


def enrich_signals_with_sentiment(signals: list[SignalRecord]) -> list[SignalRecord]:
    for signal in signals:
        result = analyze_sentiment(signal)
        signal.metadata["sentiment"] = result.label
        signal.metadata["sentiment_score"] = result.sentiment_score
        signal.metadata["frustration_score"] = result.frustration_score
        signal.metadata["pain_terms"] = result.pain_terms
    return signals


def summarize_sentiment(signals: list[SignalRecord]) -> dict[str, int]:
    labels = Counter(analyze_sentiment(signal).label for signal in signals)
    return {
        "positive": labels.get("positive", 0),
        "neutral": labels.get("neutral", 0),
        "negative": labels.get("negative", 0),
    }


def _signal_text(signal: SignalRecord) -> str:
    return f"{signal.topic} {signal.title} {signal.summary} {signal.source}".lower()


def _source_pain_bonus(signal: SignalRecord) -> int:
    if signal.category == "app_stores":
        return 10
    if signal.category == "social":
        return 8
    return 0
