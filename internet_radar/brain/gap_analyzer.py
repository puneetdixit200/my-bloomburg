from __future__ import annotations

from dataclasses import dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.scoring.master_scorer import MasterScorer
from internet_radar.signals.gap_finder import GapCluster, find_startup_gaps
from internet_radar.signals.sentiment_pipeline import analyze_sentiment
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class PainPattern:
    problem: str
    complaints: int
    pain_level: int
    representative_quote: str


@dataclass(frozen=True)
class StartupIdea:
    idea: str
    market_size: str
    competition_level: str
    technical_difficulty: str
    timing: str
    score: int


@dataclass(frozen=True)
class GapAnalysis:
    topic: str
    route: LLMChoice
    patterns: list[PainPattern]
    startup_ideas: list[StartupIdea]
    build_first: bool
    recommended_action: str


def analyze_gaps(
    signals: list[SignalRecord],
    router: LLMRouter | None = None,
    min_complaints: int = 1,
) -> list[GapAnalysis]:
    router = router or LLMRouter()
    route = router.route("gap_analysis", _content_length(signals))
    clusters = find_startup_gaps(signals, min_complaints=min_complaints)
    metadata_clusters = _metadata_clusters(signals, min_complaints=min_complaints)
    merged = {cluster.problem: cluster for cluster in clusters}
    merged.update({cluster.problem: cluster for cluster in metadata_clusters})
    return [
        _analysis_from_cluster(cluster, route)
        for cluster in sorted(merged.values(), key=lambda item: item.score, reverse=True)
    ]


def _analysis_from_cluster(cluster: GapCluster, route: LLMChoice) -> GapAnalysis:
    pattern = PainPattern(
        problem=cluster.problem,
        complaints=cluster.complaint_count,
        pain_level=cluster.pain_level,
        representative_quote=cluster.best_quote,
    )
    idea = StartupIdea(
        idea=cluster.startup_idea,
        market_size=_market_size(cluster),
        competition_level=_competition_level(cluster),
        technical_difficulty=_technical_difficulty(cluster),
        timing="now" if cluster.score >= 70 else "watch",
        score=cluster.score,
    )
    build_first = cluster.score >= 70 and cluster.pain_level >= 5
    action = "Interview users and prototype the narrow fix." if build_first else "Keep watching for more complaints."
    return GapAnalysis(
        topic=cluster.problem,
        route=route,
        patterns=[pattern],
        startup_ideas=[idea],
        build_first=build_first,
        recommended_action=action,
    )


def _market_size(cluster: GapCluster) -> str:
    if cluster.complaint_count >= 5 or cluster.score >= 80:
        return "large"
    if cluster.complaint_count >= 2 or cluster.score >= 60:
        return "medium"
    return "small"


def _competition_level(cluster: GapCluster) -> str:
    return "low" if cluster.pain_level >= 8 else "medium"


def _technical_difficulty(cluster: GapCluster) -> str:
    return "medium" if cluster.score >= 60 else "low"


def _content_length(signals: list[SignalRecord]) -> int:
    return sum(len(signal.topic) + len(signal.title) + len(signal.summary) for signal in signals)


def _metadata_clusters(signals: list[SignalRecord], min_complaints: int) -> list[GapCluster]:
    grouped: dict[str, list[tuple[SignalRecord, int]]] = {}
    for signal in signals:
        frustration = max(_as_int(signal.metadata.get("frustration_score")), analyze_sentiment(signal).frustration_score)
        if frustration < 45:
            continue
        grouped.setdefault(signal.topic.strip().lower(), []).append((signal, frustration))

    clusters: list[GapCluster] = []
    for problem, entries in grouped.items():
        if len(entries) < min_complaints:
            continue
        complaint_count = len(entries)
        pain_level = max(1, min(10, round(sum(score for _, score in entries) / complaint_count / 10)))
        best_signal, _ = max(entries, key=lambda entry: (entry[1], entry[0].score))
        formula_score = MasterScorer().score_startup_gap(
            {
                "complaint_count": complaint_count * pain_level,
                "market_score": 0.7,
                "competition_score": 0.35,
                "feasibility_score": 0.75,
                "trend_phase": "EMERGING",
            }
        )
        score = max(formula_score, min(50 + pain_level * 4 + complaint_count * 5, 100))
        clusters.append(
            GapCluster(
                problem=problem,
                complaint_count=complaint_count,
                pain_level=pain_level,
                sources=[signal.source for signal, _ in entries],
                best_quote=(best_signal.summary or best_signal.title),
                startup_idea=f"Build a simpler fix for {problem} focused on repeated pain.",
                score=score,
                signal_ids=[str(signal.id) for signal, _ in entries],
            )
        )
    return clusters


def _as_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0
