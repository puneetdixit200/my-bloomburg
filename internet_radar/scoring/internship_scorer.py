from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class InternshipScore:
    score: int
    components: dict[str, int]
    recommendation: str


class InternshipScorer:
    def score(self, job: dict[str, Any], user_profile: dict[str, Any] | None = None) -> InternshipScore:
        user_profile = user_profile or {}
        freshness = round(_freshness_score(int(job.get("posted_hours_ago", 72))) * 30)
        low_applicants = round((1 - float(job.get("applicant_ratio", 0.5))) * 25)
        company_health = round(_company_health(job) * 20)
        skill_match = round(_skill_match(str(job.get("description", "")), user_profile) * 25)
        components = {
            "freshness": freshness,
            "low_applicants": low_applicants,
            "company_health": company_health,
            "skill_match": skill_match,
        }
        score = min(sum(components.values()), 100)
        return InternshipScore(score=score, components=components, recommendation=_recommendation(score))


def _freshness_score(hours_ago: int) -> float:
    if hours_ago < 6:
        return 1.0
    if hours_ago < 24:
        return 0.8
    if hours_ago < 72:
        return 0.6
    if hours_ago < 168:
        return 0.3
    return 0.1


def _company_health(job: dict[str, Any]) -> float:
    return max(0.0, min(float(job.get("company_growth", job.get("company_health", 0.6))), 1.0))


def _skill_match(text: str, user_profile: dict[str, Any]) -> float:
    skills = [str(skill).lower() for skill in user_profile.get("skills", [])]
    if not skills:
        return 0.5
    words = set(re.findall(r"[a-z0-9.+#-]+", text.lower()))
    matched = sum(1 for skill in skills if skill in words or skill in text.lower())
    return min(matched / max(len(skills), 1), 1.0)


def _recommendation(score: int) -> str:
    if score >= 80:
        return "apply today"
    if score >= 60:
        return "shortlist"
    return "watch"
