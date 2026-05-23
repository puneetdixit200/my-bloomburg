from __future__ import annotations

from typing import Any

from internet_radar.scoring.hackathon_scorer import HackathonScorer
from internet_radar.scoring.internship_scorer import InternshipScorer
from internet_radar.scoring.startup_gap_scorer import StartupGapScorer
from internet_radar.scoring.trend_scorer import TrendScorer


class MasterScorer:
    def score_hackathon(self, hackathon: dict[str, Any], user_profile: dict[str, Any]) -> int:
        return HackathonScorer().score(hackathon, user_profile).score

    def score_internship(self, job: dict[str, Any], user_profile: dict[str, Any]) -> int:
        return InternshipScorer().score(job, user_profile).score

    def score_startup_gap(self, gap: dict[str, Any]) -> int:
        return StartupGapScorer().score(gap).score

    def score_research_signal(self, research: dict[str, Any]) -> int:
        paper_velocity = min(float(research.get("papers_per_week", 0)) * 2, 30)
        citation_growth = min(float(research.get("citation_velocity", 0)) * 2, 25)
        institution_q = min(float(research.get("top_institution_count", 0)) * 2, 20)
        github_link = 20 if research.get("has_code_repos") else 0
        industry_adopt = min(float(research.get("industry_mentions", 0)) * 5, 15)
        return round(min(paper_velocity + citation_growth + institution_q + github_link + industry_adopt, 100))

    def score_trend(self, trend: dict[str, Any]) -> int:
        return TrendScorer().score(trend).score

    def _freshness_score(self, hours_ago: int) -> float:
        if hours_ago < 6:
            return 1.0
        if hours_ago < 24:
            return 0.8
        if hours_ago < 72:
            return 0.6
        if hours_ago < 168:
            return 0.3
        return 0.1

    def _timing_bonus(self, phase: str) -> float:
        return {"EMERGING": 1.0, "ACCELERATING": 0.8, "PEAKING": 0.3, "DECLINING": 0.0}.get(phase.upper(), 0.5)

    def _trend_timing_score(self, phase: str) -> float:
        return self._timing_bonus(phase)
