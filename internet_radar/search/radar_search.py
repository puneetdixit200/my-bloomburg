from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from internet_radar.brain.deep_dive import build_deep_dive
from internet_radar.brain.relevance_scorer import score_signal_relevance
from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class SearchResult:
    signal: SignalRecord
    match_score: int
    reasons: list[str]


def search_signals(signals: list[SignalRecord], query: str, profile: UserProfile | None = None, limit: int = 20) -> list[SearchResult]:
    terms = _query_terms(query)
    results: list[SearchResult] = []
    for signal in signals:
        text = _signal_text(signal)
        term_hits = sum(1 for term in terms if term in text)
        if not term_hits:
            continue

        exact_bonus = 25 if query.lower() in text else 0
        relevance = score_signal_relevance(signal, profile) if profile else None
        relevance_bonus = relevance.score // 4 if relevance else 0
        match_score = min(signal.score + term_hits * 15 + exact_bonus + relevance_bonus, 200)
        reasons = [f"matched:{term}" for term in terms if term in text]
        if relevance:
            reasons.extend(relevance.reasons)
        results.append(SearchResult(signal=signal, match_score=match_score, reasons=reasons))

    return sorted(results, key=lambda result: (result.match_score, result.signal.score), reverse=True)[:limit]


def analyze_query(
    signals: list[SignalRecord],
    query: str,
    profile: UserProfile | None = None,
    include_deep_dive: bool = False,
) -> dict[str, object]:
    results = search_signals(signals, query, profile=profile)
    matched_signals = [result.signal for result in results]
    categories = Counter(signal.category for signal in matched_signals)
    sources = {signal.source for signal in matched_signals}
    relevance_scores = [
        score_signal_relevance(signal, profile).score
        for signal in matched_signals
        if profile is not None
    ]
    analysis: dict[str, object] = {
        "query": query,
        "matching_signals": len(matched_signals),
        "source_count": len(sources),
        "top_categories": [category for category, _ in categories.most_common(3)],
        "top_sources": sorted(sources)[:5],
        "total_velocity": sum(signal.velocity for signal in matched_signals),
        "personal_relevance": max(relevance_scores) if relevance_scores else 0,
        "top_results": [result.signal.id for result in results[:5]],
    }
    if include_deep_dive:
        analysis["deep_dive"] = build_deep_dive(query, matched_signals).as_dict()
    return analysis


def _query_terms(query: str) -> list[str]:
    return [term for term in query.lower().split() if term]


def _signal_text(signal: SignalRecord) -> str:
    return f"{signal.topic} {signal.title} {signal.summary} {signal.source} {signal.category}".lower()
