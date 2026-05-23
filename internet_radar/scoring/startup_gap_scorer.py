from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StartupGapScore:
    score: int
    components: dict[str, int]
    recommendation: str


class StartupGapScorer:
    def score(self, gap: dict[str, Any]) -> StartupGapScore:
        pain_intensity = round(min(float(gap.get("complaint_count", 0)) / 10, 30))
        market_signals = round(float(gap.get("market_score", 0.5)) * 20)
        competition_gap = round((1 - float(gap.get("competition_score", 0.5))) * 20)
        tech_feasible = round(float(gap.get("feasibility_score", 0.5)) * 15)
        timing = round(_timing_bonus(str(gap.get("trend_phase", "EMERGING"))) * 15)
        components = {
            "pain_intensity": pain_intensity,
            "market_signals": market_signals,
            "competition_gap": competition_gap,
            "tech_feasible": tech_feasible,
            "timing": timing,
        }
        score = min(sum(components.values()), 100)
        return StartupGapScore(score=score, components=components, recommendation=_recommendation(score))


def _timing_bonus(phase: str) -> float:
    return {"EMERGING": 1.0, "ACCELERATING": 0.8, "PEAKING": 0.3, "DECLINING": 0.0}.get(phase.upper(), 0.5)


def _recommendation(score: int) -> str:
    if score >= 75:
        return "validate now"
    if score >= 55:
        return "interview users"
    return "watch"
