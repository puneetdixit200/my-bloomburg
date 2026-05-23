from __future__ import annotations

from dataclasses import dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class SignalSummary:
    query: str
    route: LLMChoice
    headline: str
    key_points: list[str]
    top_sources: list[str]
    next_action: str


def summarize_signals(
    signals: list[SignalRecord],
    query: str = "all signals",
    router: LLMRouter | None = None,
) -> SignalSummary:
    router = router or LLMRouter()
    route = router.route("summarize", _content_length(query, signals))
    top_signals = sorted(signals, key=lambda signal: signal.score, reverse=True)
    top_sources = _ordered_sources(top_signals)
    top_score = top_signals[0].score if top_signals else 0
    categories = sorted({signal.category for signal in signals})
    headline = (
        f"{query} has {len(signals)} signals across {len(top_sources)} sources"
        f" with top score {top_score}."
    )
    key_points = _key_points(top_signals, categories)
    next_action = (
        f"Validate {query} with {top_sources[0]} and one independent source."
        if top_sources
        else f"Collect more sources before acting on {query}."
    )
    return SignalSummary(
        query=query,
        route=route,
        headline=headline,
        key_points=key_points,
        top_sources=top_sources,
        next_action=next_action,
    )


def _key_points(signals: list[SignalRecord], categories: list[str]) -> list[str]:
    if not signals:
        return ["No signals collected yet."]
    points = [
        f"Top signal: {signals[0].title} from {signals[0].source} scored {signals[0].score}/100.",
        f"Coverage: {', '.join(categories) if categories else 'none'}.",
    ]
    painful = [signal for signal in signals if _as_int(signal.metadata.get("frustration_score")) >= 45]
    if painful:
        points.append(f"Pain signal: {painful[0].title}")
    funding = [signal for signal in signals if signal.category == "finance"]
    if funding:
        points.append(f"Funding signal: {funding[0].title}")
    return points


def _ordered_sources(signals: list[SignalRecord]) -> list[str]:
    sources: list[str] = []
    for signal in signals:
        if signal.source not in sources:
            sources.append(signal.source)
    return sources


def _content_length(query: str, signals: list[SignalRecord]) -> int:
    return len(query) + sum(len(signal.title) + len(signal.summary) + len(signal.topic) for signal in signals)


def _as_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0
