from __future__ import annotations

from dataclasses import dataclass

from internet_radar.brain.llm_router import LLMChoice, LLMRouter
from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class IdeaValidation:
    idea: str
    score: int
    market_validation: str
    evidence: dict[str, int]
    risks: list[str]
    recommendation: str
    route: LLMChoice


def validate_idea(
    idea: str,
    signals: list[SignalRecord],
    profile: UserProfile | None = None,
    router: LLMRouter | None = None,
) -> IdeaValidation:
    router = router or LLMRouter()
    profile = profile or UserProfile()
    route = router.route("idea_generate", len(idea) + _content_length(signals))
    evidence = _evidence(signals)
    score = _score(evidence, idea, profile)
    return IdeaValidation(
        idea=idea,
        score=score,
        market_validation=_validation_label(score),
        evidence=evidence,
        risks=_risks(signals, evidence),
        recommendation=_recommendation(score),
        route=route,
    )


def validate_ideas(
    ideas: list[str],
    signals: list[SignalRecord],
    profile: UserProfile | None = None,
    router: LLMRouter | None = None,
    limit: int = 10,
) -> list[IdeaValidation]:
    router = router or LLMRouter()
    validations = [
        validate_idea(idea, signals, profile=profile, router=router)
        for idea in ideas[:limit]
        if idea.strip()
    ]
    return sorted(validations, key=lambda validation: validation.score, reverse=True)


def _evidence(signals: list[SignalRecord]) -> dict[str, int]:
    return {
        "pain": sum(
            1
            for signal in signals
            if _as_int(signal.metadata.get("frustration_score")) >= 45 or signal.category in {"social", "app_stores"}
        ),
        "funding": sum(1 for signal in signals if signal.category == "finance"),
        "research": sum(1 for signal in signals if signal.category == "research"),
        "jobs": sum(1 for signal in signals if signal.category == "jobs"),
        "code": sum(1 for signal in signals if signal.category == "code"),
        "source_count": len({signal.source for signal in signals}),
    }


def _score(evidence: dict[str, int], idea: str, profile: UserProfile) -> int:
    score = 25
    score += min(evidence["pain"] * 15, 25)
    score += min(evidence["funding"] * 20, 25)
    score += min(evidence["research"] * 12, 15)
    score += min(evidence["jobs"] * 10, 15)
    score += min(evidence["code"] * 10, 12)
    score += min(evidence["source_count"] * 3, 12)
    idea_text = idea.lower()
    if any(skill in idea_text for skill in profile.skills):
        score += 6
    return min(score, 100)


def _validation_label(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 60:
        return "moderate"
    return "weak"


def _recommendation(score: int) -> str:
    if score >= 80:
        return "build prototype"
    if score >= 60:
        return "validate with users"
    return "watch for more evidence"


def _risks(signals: list[SignalRecord], evidence: dict[str, int]) -> list[str]:
    risks: list[str] = []
    if evidence["source_count"] < 3:
        risks.append("needs broader source confirmation")
    if evidence["funding"] == 0:
        risks.append("no direct funding validation yet")
    painful = [signal for signal in signals if _as_int(signal.metadata.get("frustration_score")) >= 45]
    if painful:
        risks.append(painful[0].summary or painful[0].title)
    return risks or ["no major contradiction found"]


def _content_length(signals: list[SignalRecord]) -> int:
    return sum(len(signal.title) + len(signal.summary) + len(signal.topic) for signal in signals)


def _as_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0
