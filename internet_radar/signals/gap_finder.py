from __future__ import annotations

from dataclasses import dataclass

from internet_radar.scoring.master_scorer import MasterScorer
from internet_radar.signals.sentiment_pipeline import analyze_sentiment
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class GapCluster:
    problem: str
    complaint_count: int
    pain_level: int
    sources: list[str]
    best_quote: str
    startup_idea: str
    score: int
    signal_ids: list[str]


def find_startup_gaps(signals: list[SignalRecord], min_complaints: int = 2) -> list[GapCluster]:
    grouped: dict[str, list[tuple[SignalRecord, int]]] = {}
    for signal in signals:
        sentiment = analyze_sentiment(signal)
        if sentiment.frustration_score < 45:
            continue
        grouped.setdefault(_problem_key(signal), []).append((signal, sentiment.frustration_score))

    clusters: list[GapCluster] = []
    for problem, entries in grouped.items():
        if len(entries) < min_complaints:
            continue
        sources = [signal.source for signal, _ in entries]
        average_pain = round(sum(score for _, score in entries) / len(entries) / 10)
        pain_level = max(1, min(10, average_pain))
        best_signal, _ = max(entries, key=lambda entry: (entry[1], entry[0].score))
        best_quote = _quote_text(best_signal)
        complaint_count = len(entries)
        score = MasterScorer().score_startup_gap(
            {
                "complaint_count": complaint_count * pain_level,
                "market_score": 0.7,
                "competition_score": 0.35,
                "feasibility_score": 0.75,
                "trend_phase": "EMERGING",
            }
        )
        clusters.append(
            GapCluster(
                problem=problem,
                complaint_count=complaint_count,
                pain_level=pain_level,
                sources=sources,
                best_quote=best_quote,
                startup_idea=f"Build a simpler fix for {problem} focused on the repeated pain: {best_quote}",
                score=score,
                signal_ids=[str(signal.id) for signal, _ in entries],
            )
        )

    return sorted(clusters, key=lambda cluster: (cluster.score, cluster.pain_level, cluster.complaint_count), reverse=True)


def _problem_key(signal: SignalRecord) -> str:
    return signal.topic.strip().lower()


def _quote_text(signal: SignalRecord) -> str:
    if signal.summary:
        return f"{signal.title}: {signal.summary}"
    return signal.title
