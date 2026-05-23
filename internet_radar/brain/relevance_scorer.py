from __future__ import annotations

from dataclasses import dataclass

from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class RelevanceScore:
    score: int
    reasons: list[str]


def score_signal_relevance(signal: SignalRecord, profile: UserProfile) -> RelevanceScore:
    haystack = _signal_text(signal)
    if any(blocked in haystack for blocked in profile.blocked_topics):
        return RelevanceScore(score=0, reasons=["blocked"])

    score = 35
    reasons: list[str] = []

    for interest in profile.interests:
        if interest in haystack:
            score += 30
            reasons.append(f"interest:{interest}")

    for skill in profile.skills:
        if skill in haystack:
            score += 18
            reasons.append(f"skill:{skill}")

    for goal in profile.goals:
        if _goal_matches(goal, signal, haystack):
            score += 12
            reasons.append(f"goal:{goal}")

    score += min(signal.score // 10, 10)
    return RelevanceScore(score=min(score, 100), reasons=reasons or ["general"])


def rank_for_profile(signals: list[SignalRecord], profile: UserProfile, limit: int | None = None) -> list[SignalRecord]:
    ranked: list[tuple[int, SignalRecord]] = []
    for signal in signals:
        relevance = score_signal_relevance(signal, profile)
        if relevance.score <= 0:
            continue
        signal.metadata["relevance_score"] = relevance.score
        signal.metadata["relevance_reasons"] = relevance.reasons
        ranked.append((relevance.score + signal.score, signal))

    ordered = [signal for _, signal in sorted(ranked, key=lambda item: (item[0], item[1].score), reverse=True)]
    return ordered[:limit] if limit else ordered


def _signal_text(signal: SignalRecord) -> str:
    metadata_text = " ".join(str(value) for value in signal.metadata.values())
    return f"{signal.topic} {signal.title} {signal.summary} {signal.source} {signal.category} {metadata_text}".lower()


def _goal_matches(goal: str, signal: SignalRecord, haystack: str) -> bool:
    if "intern" in goal and signal.category == "jobs":
        return True
    if "hackathon" in goal and signal.category == "hackathons":
        return True
    if "startup" in goal and any(term in haystack for term in ["pain", "gap", "complaint", "abandoned"]):
        return True
    if "learn" in goal and signal.category in {"jobs", "research", "code"}:
        return True
    return False
