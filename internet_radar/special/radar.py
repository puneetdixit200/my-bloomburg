from __future__ import annotations

import re
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from internet_radar.storage.models import SignalRecord


IMPORTANT_TERMS = [
    "agentic ai",
    "browser automation",
    "local llm",
    "mcp",
    "rag",
    "retrieval agents",
    "autonomous agents",
    "ai safety",
    "machine learning",
    "cloud services",
]


def detect_dead_tools(
    repositories: list[dict[str, Any]],
    *,
    stale_before: datetime | None = None,
    min_stars: int = 1000,
    min_open_issues: int = 50,
) -> list[SignalRecord]:
    stale_cutoff = stale_before or datetime.now(UTC).replace(month=1, day=1)
    signals: list[SignalRecord] = []

    for repo in repositories:
        stars = _as_int(repo.get("stargazers_count"))
        issues = _as_int(repo.get("open_issues_count", repo.get("open_issues")))
        pushed_at = _parse_datetime(str(repo.get("pushed_at") or ""))
        if stars < min_stars or issues <= min_open_issues or pushed_at >= stale_cutoff:
            continue

        full_name = str(repo.get("full_name") or repo.get("name") or "unknown/repo")
        score = min(60 + stars // 1000 + issues // 10, 100)
        signals.append(
            SignalRecord(
                id=f"dead-tool:{full_name}",
                topic=full_name,
                title=f"{full_name} may be an abandoned tool opportunity",
                source="Dead Tool Detector",
                category="code",
                url=str(repo.get("html_url") or f"https://github.com/{full_name}"),
                score=score,
                velocity=issues,
                summary="Tool has meaningful usage but stale maintenance and unresolved user demand.",
                metadata={
                    "stars": stars,
                    "open_issues": issues,
                    "last_commit": pushed_at.isoformat(),
                    "opportunity": "abandoned with active user base",
                },
            )
        )

    return sorted(signals, key=lambda signal: signal.score, reverse=True)


def extract_conference_topics(entries: list[dict[str, Any]]) -> list[SignalRecord]:
    signals: list[SignalRecord] = []
    for index, entry in enumerate(entries):
        title = str(entry.get("title") or "Conference signal")
        text = f"{title} {entry.get('summary', '')}".lower()
        keywords = _extract_keywords(text)
        if not keywords:
            continue
        topic = _topic_from_keywords(keywords)
        score = min(70 + len(keywords) * 4, 100)
        signals.append(
            SignalRecord(
                id=f"conference:{index}:{topic}",
                topic=topic,
                title=title,
                source="Conference Radar",
                category="research",
                url=str(entry.get("link") or entry.get("url") or ""),
                score=score,
                velocity=len(keywords),
                summary=str(entry.get("summary") or "")[:280],
                metadata={"keywords": keywords},
            )
        )
    return sorted(signals, key=lambda signal: signal.score, reverse=True)


def track_salary_velocity(results: list[dict[str, Any]]) -> list[SignalRecord]:
    signals: list[SignalRecord] = []
    for index, result in enumerate(results):
        title = str(result.get("title") or "Salary result")
        body = str(result.get("body") or result.get("snippet") or "")
        role = _infer_role(f"{title} {body}")
        salaries = _extract_salaries(body)
        if not salaries:
            continue
        midpoint = round(mean(salaries))
        growth = _extract_growth(body)
        score = min(45 + midpoint // 5000 + growth, 100)
        signals.append(
            SignalRecord(
                id=f"salary:{index}:{role}",
                topic=role,
                title=f"{role.title()} salary signal",
                source="Salary Signal Tracker",
                category="jobs",
                url=str(result.get("href") or result.get("url") or ""),
                score=score,
                velocity=growth or midpoint,
                summary=body[:280],
                metadata={"salary_midpoint": midpoint, "growth_percent": growth},
            )
        )
    return sorted(signals, key=lambda signal: signal.score, reverse=True)


def predict_next_waves(topic_phases: dict[str, dict[str, str]]) -> list[SignalRecord]:
    signals: list[SignalRecord] = []
    for topic, phases in topic_phases.items():
        normalized = {source.lower(): phase.lower() for source, phase in phases.items()}
        early_research = normalized.get("arxiv") == "active"
        early_code = normalized.get("github") == "active"
        dev_validation = normalized.get("hackernews") in {"active", "warming"}
        mainstream_quiet = all(normalized.get(source, "quiet") == "quiet" for source in ["reddit", "linkedin", "youtube", "jobs"])
        if not (early_research and early_code and mainstream_quiet):
            continue

        confidence = 92 if dev_validation else 85
        signals.append(
            SignalRecord(
                id=f"wave:{topic.lower()}",
                topic=topic.lower(),
                title=f"{topic} is in an early mover window",
                source="Wave Predictor",
                category="research",
                url="",
                score=confidence,
                velocity=3,
                summary="Research and code signals are active before mainstream channels heat up.",
                metadata={
                    "wave_position": "EARLY - ACT NOW",
                    "estimated_mainstream": "3-9 months",
                    "recommended_action": "learn + build + write about it",
                    "phases": normalized,
                },
            )
        )
    return sorted(signals, key=lambda signal: signal.score, reverse=True)


def build_special_signals() -> list[SignalRecord]:
    signals: list[SignalRecord] = []
    signals.extend(
        detect_dead_tools(
            [
                {
                    "full_name": "abandoned-ai/browser-agent",
                    "stargazers_count": 3600,
                    "pushed_at": "2025-01-15T00:00:00Z",
                    "open_issues_count": 128,
                    "html_url": "https://github.com/abandoned-ai/browser-agent",
                }
            ],
            stale_before=datetime(2025, 12, 1, tzinfo=UTC),
        )
    )
    signals.extend(
        extract_conference_topics(
            [
                {
                    "title": "Workshop: Agentic AI for Browser Automation",
                    "link": "https://example.com/conference/agentic-browser-automation",
                    "summary": "Local LLM agents, browser automation, and safety evaluation.",
                }
            ]
        )
    )
    signals.extend(
        track_salary_velocity(
            [
                {
                    "title": "Machine Learning Engineer salaries",
                    "href": "https://levels.fyi/ml",
                    "body": "Machine learning engineer compensation ranges from $180k to $260k, up 28% this year.",
                }
            ]
        )
    )
    signals.extend(
        predict_next_waves(
            {
                "browser agents": {
                    "arxiv": "active",
                    "github": "active",
                    "hackernews": "active",
                    "reddit": "quiet",
                    "linkedin": "quiet",
                    "youtube": "quiet",
                    "jobs": "quiet",
                }
            }
        )
    )
    return signals


def _parse_datetime(value: str) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _extract_keywords(text: str) -> list[str]:
    keywords = [term for term in IMPORTANT_TERMS if term in text]
    return list(dict.fromkeys(keywords))


def _topic_from_keywords(keywords: list[str]) -> str:
    if "agentic ai" in keywords:
        return "agentic ai"
    if "machine learning" in keywords:
        return "machine learning"
    return keywords[0]


def _extract_salaries(text: str) -> list[int]:
    values = []
    for match in re.finditer(r"\$?\s*(\d{2,3})(?:,\d{3})?\s*k", text, flags=re.I):
        values.append(int(match.group(1)) * 1000)
    for match in re.finditer(r"\$\s*(\d{2,3}),(\d{3})", text):
        values.append(int(match.group(1)) * 1000 + int(match.group(2)))
    return values


def _extract_growth(text: str) -> int:
    match = re.search(r"(?:up|increased|growth)\s+(\d{1,3})%", text, flags=re.I)
    return int(match.group(1)) if match else 0


def _infer_role(text: str) -> str:
    lower = text.lower()
    if "machine learning" in lower:
        return "machine learning engineer"
    if "frontend" in lower:
        return "frontend developer"
    if "data engineer" in lower:
        return "data engineer"
    if "ai engineer" in lower:
        return "ai engineer"
    return "software engineer"
