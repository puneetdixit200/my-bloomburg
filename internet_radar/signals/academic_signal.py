from __future__ import annotations

from collections.abc import Iterable
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

from internet_radar.scoring.research_signal_scorer import ResearchSignalScorer
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class AcademicSignal:
    topic: str
    score: int
    papers_per_week: int
    citation_velocity: int
    top_institution_count: int
    has_code_repos: bool
    industry_lag_months: str
    recommended_skill: str
    sources: list[str]
    signal_ids: list[str]


def build_academic_signals(records: list[SignalRecord], now: datetime | None = None) -> list[AcademicSignal]:
    now = now or datetime.now(UTC)
    grouped: dict[str, list[SignalRecord]] = defaultdict(list)
    for record in records:
        if record.category == "research":
            grouped[_topic_key(record.topic)].append(record)

    academic_signals: list[AcademicSignal] = []
    scorer = ResearchSignalScorer()
    for topic, topic_records in grouped.items():
        papers_per_week = _papers_per_week(topic_records, now)
        citation_velocity = sum(_as_int(record.metadata.get("citations")) for record in topic_records)
        institutions = _unique(
            institution
            for record in topic_records
            for institution in record.metadata.get("institutions", [])
            if institution
        )
        has_code_repos = any(
            record.source == "Papers With Code" or _as_int(record.metadata.get("repo_stars")) > 0
            for record in topic_records
        )
        score_input = {
            "topic": topic,
            "papers_per_week": papers_per_week,
            "citation_velocity": citation_velocity,
            "top_institution_count": len(institutions),
            "has_code_repos": has_code_repos,
            "industry_mentions": len(_unique(record.source for record in topic_records)),
        }
        scored = scorer.score(score_input)
        observed_score = round(sum(record.score for record in topic_records) / len(topic_records))
        source_bonus = min(len(_unique(record.source for record in topic_records)) * 3, 12)
        academic_signals.append(
            AcademicSignal(
                topic=topic,
                score=max(scored.score, min(observed_score + source_bonus, 100)),
                papers_per_week=papers_per_week,
                citation_velocity=citation_velocity,
                top_institution_count=len(institutions),
                has_code_repos=has_code_repos,
                industry_lag_months=scored.industry_lag_months,
                recommended_skill=scored.recommended_skill,
                sources=_unique(record.source for record in topic_records),
                signal_ids=[str(record.id) for record in topic_records],
            )
        )

    return sorted(academic_signals, key=lambda signal: (signal.score, signal.papers_per_week), reverse=True)


def _papers_per_week(records: list[SignalRecord], now: datetime) -> int:
    recent = 0
    for record in records:
        published_at = str(record.metadata.get("published_at") or "")
        if not published_at:
            recent += 1
            continue
        try:
            observed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        except ValueError:
            recent += 1
            continue
        if (now - observed).days <= 7:
            recent += 1
    return recent


def _topic_key(topic: str) -> str:
    return " ".join(topic.strip().lower().split())


def _unique(values: Iterable[object]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        text = str(value)
        if text not in seen:
            unique_values.append(text)
            seen.add(text)
    return unique_values


def _as_int(value: object) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return 0
