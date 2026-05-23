from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from internet_radar.storage.models import SignalRecord, UserProfile


@dataclass(frozen=True)
class AlertMessage:
    signal_id: str
    kind: str
    title: str
    body: str
    channels: list[str]
    score: int


def signals_above_threshold(signals: list[SignalRecord], threshold: int = 80) -> list[SignalRecord]:
    return [signal for signal in signals if signal.score >= threshold]


def build_alerts(signals: list[SignalRecord], profile: UserProfile | None = None) -> list[AlertMessage]:
    profile = profile or UserProfile()
    channels = profile.notification_channels or ["ntfy"]
    alerts: list[AlertMessage] = []

    for signal in signals:
        if _is_blocked(signal, profile):
            continue
        score = _alert_score(signal)
        if score < profile.alert_threshold:
            continue
        alerts.append(format_alert(signal, channels=channels, score=score))

    return sorted(alerts, key=lambda alert: alert.score, reverse=True)


def format_alert(signal: SignalRecord, channels: list[str] | None = None, score: int | None = None) -> AlertMessage:
    kind = _alert_kind(signal)
    title = _alert_title(kind)
    metadata = signal.metadata
    resolved_score = score if score is not None else _alert_score(signal)

    if kind == "HACKATHON":
        body = _format_hackathon(signal, metadata, resolved_score)
    elif kind == "STARTUP_GAP":
        body = _format_startup_gap(signal, metadata, resolved_score)
    elif kind == "RESEARCH_SIGNAL":
        body = _format_research(signal, metadata, resolved_score)
    elif kind == "FUNDING_ALERT":
        body = _format_funding(signal, metadata, resolved_score)
    else:
        body = _format_skill(signal, metadata, resolved_score)

    return AlertMessage(
        signal_id=str(signal.id),
        kind=kind,
        title=title,
        body=body,
        channels=channels or ["ntfy"],
        score=resolved_score,
    )


def _alert_score(signal: SignalRecord) -> int:
    relevance_score = signal.metadata.get("relevance_score", 0)
    if isinstance(relevance_score, (int, float)):
        return int(max(signal.score, relevance_score))
    return signal.score


def _alert_kind(signal: SignalRecord) -> str:
    explicit = str(signal.metadata.get("alert_type", "")).upper()
    if explicit:
        return explicit
    if signal.category == "hackathons":
        return "HACKATHON"
    if signal.category == "research":
        return "RESEARCH_SIGNAL"
    if signal.category == "finance":
        return "FUNDING_ALERT"
    if signal.metadata.get("pain_level") or signal.metadata.get("complaint_count") or signal.category in {"social", "app_stores"}:
        return "STARTUP_GAP"
    return "SKILL_RADAR"


def _alert_title(kind: str) -> str:
    return {
        "HACKATHON": "HIGH OPPORTUNITY - HACKATHON",
        "STARTUP_GAP": "STARTUP GAP DETECTED",
        "RESEARCH_SIGNAL": "ACADEMIC SIGNAL -> FUTURE TREND",
        "FUNDING_ALERT": "VC MONEY DETECTED -> SECTOR SIGNAL",
        "SKILL_RADAR": "SKILL TO LEARN NOW",
    }.get(kind, kind.replace("_", " "))


def _format_hackathon(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    sponsors = _join(metadata.get("sponsors"), default="unknown")
    return "\n".join(
        [
            "HIGH OPPORTUNITY - HACKATHON",
            "",
            f"Name: {signal.title}",
            f"Prize: {_money(metadata.get('prize'))}",
            f"Teams now: {metadata.get('participants', 'unknown')}",
            f"Deadline: {metadata.get('days_left', 'unknown')} days",
            f"Remote: {metadata.get('remote', 'unknown')}",
            f"Sponsors: {sponsors}",
            f"Theme: {metadata.get('theme', signal.topic)}",
            "",
            f"SCORE: {score}/100",
            "",
            "WHY NOW:",
            str(metadata.get("reasoning", signal.summary or "High-scoring opportunity signal.")),
            signal.url,
        ]
    ).strip()


def _format_startup_gap(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            "STARTUP GAP DETECTED",
            "",
            f"Category: {signal.topic}",
            f"Pain Level: {metadata.get('pain_level', 'unknown')}/10",
            f"Complaints found: {metadata.get('complaint_count', 'unknown')}",
            "",
            "TOP PAIN QUOTE:",
            str(metadata.get("best_quote", signal.summary or signal.title)),
            "",
            f"GAP SCORE: {score}/100",
            signal.url,
        ]
    ).strip()


def _format_research(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            "ACADEMIC SIGNAL -> FUTURE TREND",
            "",
            f"Topic: {signal.topic}",
            f"Papers this week: {metadata.get('papers_week', 'unknown')} (+{metadata.get('growth', 'unknown')}% vs last week)",
            f"Top paper: {signal.title}",
            "",
            "WHY MATTERS:",
            "Academic spike now can precede industry demand.",
            "",
            f"SKILL TO LEARN: {metadata.get('recommended_skill', signal.topic)}",
            f"SCORE: {score}/100",
            signal.url,
        ]
    ).strip()


def _format_funding(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            "VC MONEY DETECTED -> SECTOR SIGNAL",
            "",
            f"Company: {metadata.get('company', signal.title)}",
            f"Amount: {_money(metadata.get('amount'))}",
            f"Sector: {metadata.get('sector', signal.topic)}",
            "",
            "WHAT THIS MEANS:",
            str(metadata.get("analysis", signal.summary or "Funding validates market demand.")),
            "",
            f"SCORE: {score}/100",
            signal.url,
        ]
    ).strip()


def _format_skill(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    skill = metadata.get("skill", signal.topic)
    return "\n".join(
        [
            "SKILL TO LEARN NOW",
            "",
            f"Skill: {skill}",
            f"Job postings: +{metadata.get('job_growth', 'unknown')}% this month",
            f"GitHub repos: +{metadata.get('github_growth', 'unknown')}% this month",
            f"Papers: +{metadata.get('paper_growth', 'unknown')}% this month",
            "",
            f"Opportunity: {signal.title}",
            f"SCORE: {score}/100",
            signal.url,
        ]
    ).strip()


def _money(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"${value:,.0f}"
    if value:
        return str(value)
    return "unknown"


def _join(value: object, default: str = "") -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if value:
        return str(value)
    return default


def _is_blocked(signal: SignalRecord, profile: UserProfile) -> bool:
    haystack = f"{signal.topic} {signal.title} {signal.summary} {signal.source}".lower()
    return any(blocked in haystack for blocked in profile.blocked_topics)
