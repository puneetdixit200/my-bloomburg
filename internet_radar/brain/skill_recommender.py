from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class SkillRecommendation:
    skill: str
    score: int
    demand_signals: int
    sources: list[str]
    topics: list[str]
    learning_path: list[str]
    reason: str


KEYWORD_SKILLS = {
    "agent": "agents",
    "agents": "agents",
    "browser automation": "playwright",
    "chromium": "playwright",
    "llm": "llm",
    "local llm": "ollama",
    "ollama": "ollama",
    "mcp": "mcp",
    "model context": "mcp",
    "playwright": "playwright",
    "python": "python",
    "rag": "rag",
    "streamlit": "streamlit",
    "typescript": "typescript",
}


def recommend_skills(
    signals: list[SignalRecord],
    profile: UserProfile | None = None,
    limit: int = 10,
) -> list[SkillRecommendation]:
    profile = profile or UserProfile()
    known_skills = {skill.lower() for skill in profile.skills}
    buckets: dict[str, list[SignalRecord]] = defaultdict(list)

    for signal in signals:
        for skill in _extract_skills(signal):
            if skill not in known_skills:
                buckets[skill].append(signal)

    recommendations = [
        _build_recommendation(skill, records)
        for skill, records in buckets.items()
        if records and skill not in known_skills
    ]
    return sorted(recommendations, key=lambda item: (item.score, item.demand_signals, len(item.sources)), reverse=True)[
        :limit
    ]


def _extract_skills(signal: SignalRecord) -> set[str]:
    skills: set[str] = set()
    metadata_skills = signal.metadata.get("skills", [])
    if isinstance(metadata_skills, list):
        skills.update(str(skill).strip().lower() for skill in metadata_skills if str(skill).strip())

    text = f"{signal.topic} {signal.title} {signal.summary}".lower()
    for needle, skill in KEYWORD_SKILLS.items():
        if needle in text:
            skills.add(skill)

    # Preserve concrete tech names that appear in titles even when metadata is sparse.
    for token in re.findall(r"[a-z][a-z0-9.+#-]{2,}", text):
        if token in KEYWORD_SKILLS:
            skills.add(KEYWORD_SKILLS[token])

    if "ollama" in skills:
        skills.discard("llm")
        skills.discard("agents")
    if "playwright" in skills:
        skills.discard("agents")
    return skills


def _build_recommendation(skill: str, records: list[SignalRecord]) -> SkillRecommendation:
    sources: list[str] = []
    topics: list[str] = []
    for signal in records:
        if signal.source not in sources:
            sources.append(signal.source)
        if signal.topic not in topics:
            topics.append(signal.topic)

    average_score = sum(signal.score for signal in records) / len(records)
    average_velocity = sum(signal.velocity for signal in records) / len(records)
    score = round(
        average_score * 0.65
        + min(len(records) * 12, 28)
        + min(len(sources) * 5, 15)
        + min(average_velocity / 3, 8)
    )
    score = max(0, min(100, score))

    return SkillRecommendation(
        skill=skill,
        score=score,
        demand_signals=len(records),
        sources=sources,
        topics=topics[:5],
        learning_path=_learning_path(skill),
        reason=f"{skill} appears in {len(records)} high-signal records across {len(sources)} sources.",
    )


def _learning_path(skill: str) -> list[str]:
    return [
        f"Build one small {skill} project tied to your profile interests.",
        f"Read the top {skill} code or research signal from today's radar.",
        f"Publish a short {skill} demo or note so the signal becomes portfolio evidence.",
    ]
