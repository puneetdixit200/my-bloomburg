from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ResearchSignalScore:
    score: int
    components: dict[str, int]
    recommended_skill: str
    industry_lag_months: str


class ResearchSignalScorer:
    def score(self, research: dict[str, Any]) -> ResearchSignalScore:
        components = {
            "paper_velocity": round(min(float(research.get("papers_per_week", 0)) * 2, 30)),
            "citation_growth": round(min(float(research.get("citation_velocity", 0)) * 2, 25)),
            "institution_quality": round(min(float(research.get("top_institution_count", 0)) * 2, 20)),
            "github_code": 20 if research.get("has_code_repos") else 0,
            "industry_adoption": round(min(float(research.get("industry_mentions", 0)) * 5, 15)),
        }
        score = min(sum(components.values()), 100)
        return ResearchSignalScore(
            score=score,
            components=components,
            recommended_skill=str(research.get("recommended_skill") or research.get("topic") or "research literacy"),
            industry_lag_months="12-18",
        )
