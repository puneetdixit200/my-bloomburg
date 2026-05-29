from __future__ import annotations

from dataclasses import asdict, dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class DeepDiveReport:
    query: str
    route: LLMChoice
    executive_summary: str
    opportunities: list[str]
    risks: list[str]
    sources: list[str]
    suggested_actions: list[str]

    def as_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["route"] = asdict(self.route)
        return data


def build_deep_dive(query: str, signals: list[SignalRecord], router: LLMRouter | None = None) -> DeepDiveReport:
    router = router or LLMRouter()
    route = router.route("gap_analysis", _content_length(query, signals))
    sources = _ordered_sources(signals)
    categories = sorted({signal.category for signal in signals})
    painful = [signal for signal in signals if _pain_score(signal) >= 45]
    research = [signal for signal in signals if signal.category == "research"]
    funding = [signal for signal in signals if signal.category == "finance"]

    executive_summary = (
        f"{query} has {len(signals)} signals across {len(sources)} sources"
        f". Categories: {', '.join(categories) or 'none'}."
    )
    opportunities = _opportunities(query, painful, research, funding)
    risks = _risks(signals, painful)
    actions = _actions(query, opportunities, risks, sources)

    return DeepDiveReport(
        query=query,
        route=route,
        executive_summary=executive_summary,
        opportunities=opportunities,
        risks=risks,
        sources=sources,
        suggested_actions=actions,
    )


def _content_length(query: str, signals: list[SignalRecord]) -> int:
    return len(query) + sum(len(signal.title) + len(signal.summary) + len(signal.topic) for signal in signals)


def _ordered_sources(signals: list[SignalRecord]) -> list[str]:
    sources: list[str] = []
    for signal in signals:
        if signal.source not in sources:
            sources.append(signal.source)
    return sources


def _pain_score(signal: SignalRecord) -> int:
    value = signal.metadata.get("frustration_score", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _opportunities(query: str, painful: list[SignalRecord], research: list[SignalRecord], funding: list[SignalRecord]) -> list[str]:
    opportunities: list[str] = []
    if painful:
        opportunities.append(f"Startup gap: simplify {query} around repeated user pain.")
    if research:
        opportunities.append(f"Learning edge: research velocity suggests {query} skills may compound early.")
    if funding:
        opportunities.append(f"Market validation: funding signals suggest budgets are forming around {query}.")
    return opportunities or [f"Track {query} until more source confirmation appears."]


def _risks(signals: list[SignalRecord], painful: list[SignalRecord]) -> list[str]:
    risks: list[str] = []
    for signal in painful[:3]:
        risks.append(signal.summary or signal.title)
    if len({signal.source for signal in signals}) < 3:
        risks.append("Needs more cross-source confirmation before acting aggressively.")
    return risks or ["No major negative signal detected yet."]


def _actions(query: str, opportunities: list[str], risks: list[str], sources: list[str]) -> list[str]:
    first_source = sources[0] if sources else "primary sources"
    return [
        f"Validate {query} against {first_source} and one independent source.",
        f"Prototype one response to: {opportunities[0]}",
        f"Monitor risk: {risks[0]}",
    ]
