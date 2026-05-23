from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HackathonScore:
    score: int
    components: dict[str, int]
    recommendation: str


class HackathonScorer:
    def score(self, hackathon: dict[str, Any], user_profile: dict[str, Any] | None = None) -> HackathonScore:
        user_profile = user_profile or {}
        prize_score = round(min(math.log10(float(hackathon.get("prize_pool", 0)) + 1) * 12, 30))
        crowd_score = round((1 - float(hackathon.get("crowd_ratio", 0.5))) * 25)
        urgency_score = round(_urgency(int(hackathon.get("days_left", 14))) * 15)
        sponsor_score = round(_sponsor_quality(hackathon.get("sponsors", [])) * 15)
        remote_score = 10 if hackathon.get("is_remote", True) else 0
        skill_match = round(_skill_match(str(hackathon.get("theme", "")), user_profile) * 5)
        components = {
            "prize_score": prize_score,
            "crowd_score": crowd_score,
            "urgency_score": urgency_score,
            "sponsor_score": sponsor_score,
            "remote_score": remote_score,
            "skill_match": skill_match,
        }
        score = min(sum(components.values()), 100)
        return HackathonScore(score=score, components=components, recommendation=_recommendation(score))


def _urgency(days_left: int) -> float:
    if days_left <= 0:
        return 0.0
    if days_left <= 7:
        return 1.0
    if days_left <= 21:
        return 0.7
    return 0.4


def _sponsor_quality(sponsors: list[str] | str) -> float:
    if isinstance(sponsors, str):
        sponsors = [sponsors]
    premium = {"nvidia", "openai", "google", "microsoft", "meta", "aws", "yc"}
    text = " ".join(str(sponsor) for sponsor in sponsors).lower()
    return 1.0 if any(name in text for name in premium) else min(len(sponsors) / 3, 0.7)


def _skill_match(text: str, user_profile: dict[str, Any]) -> float:
    skills = [str(skill).lower() for skill in user_profile.get("skills", [])]
    if not skills:
        return 0.5
    words = set(re.findall(r"[a-z0-9.+#-]+", text.lower()))
    matched = sum(1 for skill in skills if skill in words or skill in text.lower())
    return min(matched / max(len(skills), 1), 1.0)


def _recommendation(score: int) -> str:
    if score >= 85:
        return "apply now"
    if score >= 65:
        return "watch"
    return "wait"
