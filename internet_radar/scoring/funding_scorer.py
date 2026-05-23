from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FundingScore:
    score: int
    components: dict[str, int]
    market_validation: str


class FundingScorer:
    def score(self, funding: dict[str, Any]) -> FundingScore:
        amount = float(funding.get("amount", funding.get("funding_amount", 0)) or 0)
        investors = funding.get("investors", [])
        if isinstance(investors, str):
            investors = [investors]
        days_ago = int(funding.get("days_ago", funding.get("age_days", 30)) or 30)
        related_jobs = int(funding.get("related_jobs", funding.get("job_count", 0)) or 0)
        sector = str(funding.get("sector", "")).lower()

        components = {
            "amount_signal": round(min(math.log10(amount + 1) * 5, 35)),
            "investor_quality": _investor_quality([str(investor) for investor in investors]),
            "freshness": _freshness(days_ago),
            "hiring_signal": min(related_jobs * 3, 15),
            "sector_signal": 10 if any(term in sector for term in ["ai", "developer", "automation", "agent"]) else 5,
        }
        score = min(sum(components.values()), 100)
        return FundingScore(score=score, components=components, market_validation=_validation_label(score))


def _investor_quality(investors: list[str]) -> int:
    premium = {"a16z", "sequoia", "yc", "accel", "benchmark", "greylock", "lightspeed"}
    text = " ".join(investors).lower()
    premium_hits = sum(1 for investor in premium if investor in text)
    if premium_hits:
        return min(10 + premium_hits * 5, 20)
    return min(len(investors) * 4, 12)


def _freshness(days_ago: int) -> int:
    if days_ago <= 7:
        return 20
    if days_ago <= 30:
        return 15
    if days_ago <= 90:
        return 8
    return 3


def _validation_label(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 55:
        return "medium"
    return "watch"
