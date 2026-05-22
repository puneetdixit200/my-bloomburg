from __future__ import annotations

import math
import re
from typing import Any


class MasterScorer:
    def score_hackathon(self, hackathon: dict[str, Any], user_profile: dict[str, Any]) -> int:
        prize_score = min(math.log10(float(hackathon.get("prize_pool", 0)) + 1) * 12, 30)
        crowd_score = (1 - float(hackathon.get("crowd_ratio", 0.5))) * 25
        urgency_score = self._urgency(int(hackathon.get("days_left", 14))) * 15
        sponsor_score = self._sponsor_quality(hackathon.get("sponsors", [])) * 15
        remote_score = 10 if hackathon.get("is_remote", True) else 0
        skill_match = self._skill_match(str(hackathon.get("theme", "")), user_profile) * 5
        return round(min(prize_score + crowd_score + urgency_score + sponsor_score + remote_score + skill_match, 100))

    def score_internship(self, job: dict[str, Any], user_profile: dict[str, Any]) -> int:
        freshness = self._freshness_score(int(job.get("posted_hours_ago", 72))) * 30
        low_applicants = (1 - float(job.get("applicant_ratio", 0.5))) * 25
        company_health = self._company_health(job) * 20
        skill_match = self._skill_match(str(job.get("description", "")), user_profile) * 25
        return round(min(freshness + low_applicants + company_health + skill_match, 100))

    def score_startup_gap(self, gap: dict[str, Any]) -> int:
        pain_intensity = min(float(gap.get("complaint_count", 0)) / 10, 30)
        market_signals = float(gap.get("market_score", 0.5)) * 20
        competition_gap = (1 - float(gap.get("competition_score", 0.5))) * 20
        tech_feasible = float(gap.get("feasibility_score", 0.5)) * 15
        timing = self._trend_timing_score(str(gap.get("trend_phase", "EMERGING"))) * 15
        return round(min(pain_intensity + market_signals + competition_gap + tech_feasible + timing, 100))

    def score_research_signal(self, research: dict[str, Any]) -> int:
        paper_velocity = min(float(research.get("papers_per_week", 0)) * 2, 30)
        citation_growth = min(float(research.get("citation_velocity", 0)) * 2, 25)
        institution_q = min(float(research.get("top_institution_count", 0)) * 2, 20)
        github_link = 20 if research.get("has_code_repos") else 0
        industry_adopt = min(float(research.get("industry_mentions", 0)) * 5, 15)
        return round(min(paper_velocity + citation_growth + institution_q + github_link + industry_adopt, 100))

    def score_trend(self, trend: dict[str, Any]) -> int:
        velocity = min(float(trend.get("velocity_score", 0)), 30)
        source_count = min(float(trend.get("confirming_sources", 0)) * 5, 25)
        timing = self._timing_bonus(str(trend.get("phase", "EMERGING"))) * 25
        funding = 20 if trend.get("funding_detected") else 0
        return round(min(velocity + source_count + timing + funding, 100))

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

    def _urgency(self, days_left: int) -> float:
        if days_left <= 0:
            return 0.0
        if days_left <= 7:
            return 1.0
        if days_left <= 21:
            return 0.7
        return 0.4

    def _sponsor_quality(self, sponsors: list[str] | str) -> float:
        if isinstance(sponsors, str):
            sponsors = [sponsors]
        premium = {"nvidia", "openai", "google", "microsoft", "meta", "aws", "yc"}
        text = " ".join(sponsors).lower()
        return 1.0 if any(name in text for name in premium) else min(len(sponsors) / 3, 0.7)

    def _company_health(self, job: dict[str, Any]) -> float:
        return max(0.0, min(float(job.get("company_growth", job.get("company_health", 0.6))), 1.0))

    def _skill_match(self, text: str, user_profile: dict[str, Any]) -> float:
        skills = [str(skill).lower() for skill in user_profile.get("skills", [])]
        if not skills:
            return 0.5
        words = set(re.findall(r"[a-z0-9.+#-]+", text.lower()))
        matched = sum(1 for skill in skills if skill in words or skill in text.lower())
        return min(matched / max(len(skills), 1), 1.0)
