from __future__ import annotations

from typing import Any

from internet_radar.storage.models import SignalRecord


ALERT_TEMPLATES = {
    "HACKATHON": "HIGH OPPORTUNITY - HACKATHON",
    "STARTUP_GAP": "STARTUP GAP DETECTED",
    "RESEARCH_SIGNAL": "ACADEMIC SIGNAL -> FUTURE TREND",
    "FUNDING_ALERT": "VC MONEY DETECTED -> SECTOR SIGNAL",
    "SKILL_RADAR": "SKILL TO LEARN NOW",
}


def render_alert_template(kind: str, signal: SignalRecord, score: int) -> str:
    metadata = signal.metadata
    normalized_kind = kind.upper()
    if normalized_kind == "HACKATHON":
        return _format_hackathon(signal, metadata, score)
    if normalized_kind == "STARTUP_GAP":
        return _format_startup_gap(signal, metadata, score)
    if normalized_kind == "RESEARCH_SIGNAL":
        return _format_research(signal, metadata, score)
    if normalized_kind == "FUNDING_ALERT":
        return _format_funding(signal, metadata, score)
    return _format_skill(signal, metadata, score)


def alert_title(kind: str) -> str:
    return ALERT_TEMPLATES.get(kind.upper(), kind.replace("_", " "))


def _format_hackathon(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    sponsors = _join(metadata.get("sponsors"), default="unknown")
    return "\n".join(
        [
            ALERT_TEMPLATES["HACKATHON"],
            "",
            f"Name: {signal.title}",
            f"Prize: {_money(metadata.get('prize'))}",
            f"Teams now: {_value(metadata.get('participants'))}",
            f"Deadline: {_value(metadata.get('days_left'))} days",
            f"Remote: {_value(metadata.get('remote'))}",
            f"Sponsors: {sponsors}",
            f"Theme: {_value(metadata.get('theme'), signal.topic)}",
            "",
            f"SCORE: {score}/100",
            "",
            "WHY NOW:",
            str(metadata.get("reasoning", signal.summary or "High-scoring opportunity signal.")),
            _value(signal.url, ""),
        ]
    ).strip()


def _format_startup_gap(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            ALERT_TEMPLATES["STARTUP_GAP"],
            "",
            f"Category: {signal.topic}",
            f"Pain Level: {_value(metadata.get('pain_level'))}/10",
            f"Sources: {_join(metadata.get('sources_confirming'), default=_value(signal.source))}",
            f"Complaints found: {_value(metadata.get('complaint_count'))}",
            "",
            "TOP PAIN QUOTE:",
            str(metadata.get("best_quote", signal.summary or signal.title)),
            "",
            f"Startup idea: {_value(metadata.get('llm_idea'), metadata.get('startup_idea', 'unknown'))}",
            f"GAP SCORE: {score}/100",
            _value(signal.url, ""),
        ]
    ).strip()


def _format_research(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            ALERT_TEMPLATES["RESEARCH_SIGNAL"],
            "",
            f"Topic: {signal.topic}",
            f"Papers this week: {_value(metadata.get('papers_week'))} (+{_value(metadata.get('growth'))}% vs last week)",
            f"Top institutions: {_join(metadata.get('institutions'), default='unknown')}",
            f"GitHub repos with code: {_value(metadata.get('code_repos'))}",
            "",
            "WHY MATTERS:",
            "Academic spike now can precede industry demand.",
            "",
            f"Top paper: {signal.title}",
            f"SKILL TO LEARN: {_value(metadata.get('recommended_skill'), signal.topic)}",
            f"SCORE: {score}/100",
            _value(signal.url, ""),
        ]
    ).strip()


def _format_funding(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    return "\n".join(
        [
            ALERT_TEMPLATES["FUNDING_ALERT"],
            "",
            f"Company: {_value(metadata.get('company'), signal.title)}",
            f"Amount: {_money(metadata.get('amount'))}",
            f"Date: {_value(metadata.get('date'))}",
            f"Sector: {_value(metadata.get('sector'), signal.topic)}",
            f"Investors: {_join(metadata.get('investors'), default='unknown')}",
            "",
            "WHAT THIS MEANS:",
            str(metadata.get("analysis", signal.summary or "Funding validates market demand.")),
            "",
            f"SCORE: {score}/100",
            _value(signal.url, ""),
        ]
    ).strip()


def _format_skill(signal: SignalRecord, metadata: dict[str, Any], score: int) -> str:
    skill = _value(metadata.get("skill"), signal.topic)
    return "\n".join(
        [
            ALERT_TEMPLATES["SKILL_RADAR"],
            "",
            f"Skill: {skill}",
            f"Job postings: +{_value(metadata.get('job_growth'))}% this month",
            f"GitHub repos: +{_value(metadata.get('github_growth'))}% this month",
            f"Papers: +{_value(metadata.get('paper_growth'))}% this month",
            "",
            f"Timing: {_value(metadata.get('timing_window'))}",
            f"Difficulty: {_value(metadata.get('difficulty'))}",
            f"Opportunity: {signal.title}",
            "",
            f"Learn from: {_join(metadata.get('resources'), default='unknown')}",
            f"SCORE: {score}/100",
            _value(signal.url, ""),
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


def _value(value: object, default: object = "unknown") -> str:
    if value is None or value == "":
        return str(default)
    return str(value)
