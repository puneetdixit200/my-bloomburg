from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TrendScore:
    score: int
    components: dict[str, int]
    phase: str


class TrendScorer:
    def score(self, trend: dict[str, Any]) -> TrendScore:
        phase = str(trend.get("phase", "EMERGING")).upper()
        velocity_score = round(min(float(trend.get("velocity_score", trend.get("velocity", 0))), 30))
        source_count = round(min(float(trend.get("confirming_sources", 0)) * 5, 25))
        timing_score = round(_timing_bonus(phase) * 25)
        funding_bonus = 20 if trend.get("funding_detected") else 0
        components = {
            "velocity_score": velocity_score,
            "source_count": source_count,
            "timing_score": timing_score,
            "funding_bonus": funding_bonus,
        }
        score = min(sum(components.values()), 100)
        return TrendScore(score=score, components=components, phase=phase)


def _timing_bonus(phase: str) -> float:
    return {"EMERGING": 1.0, "ACCELERATING": 0.8, "PEAKING": 0.3, "DECLINING": 0.0}.get(phase.upper(), 0.5)
