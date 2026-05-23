from __future__ import annotations

from typing import Any

from internet_radar.storage.models import SignalRecord


def write_daily_briefing(
    signals: list[SignalRecord],
    active_sources: int = 0,
    llm_status: str = "unknown",
    limit: int = 5,
) -> dict[str, Any]:
    ranked = sorted(signals, key=lambda signal: (signal.score, signal.velocity), reverse=True)
    top_signal = ranked[0] if ranked else None
    act_now = [_brief_signal(signal) for signal in ranked if signal.score >= 85][:limit]
    if not act_now:
        act_now = [_brief_signal(signal) for signal in ranked[: min(limit, 3)]]

    job_market = [_brief_signal(signal) for signal in ranked if signal.category == "jobs"][:limit]
    research = [_brief_signal(signal) for signal in ranked if signal.category == "research"][:limit]
    opportunities = [_brief_signal(signal) for signal in ranked if signal.category in {"hackathons", "finance", "app_stores"}][
        :limit
    ]

    headline = top_signal.topic if top_signal else "no signals"
    return {
        "headline": headline,
        "metrics": {
            "active_sources": active_sources,
            "signals_24h": len(ranked),
            "llm_status": llm_status,
        },
        "act_now": act_now,
        "job_market": job_market,
        "research": research,
        "opportunities": opportunities,
        "narrative": _narrative(top_signal, ranked, active_sources),
    }


def _brief_signal(signal: SignalRecord) -> dict[str, Any]:
    return {
        "topic": signal.topic,
        "title": signal.title,
        "source": signal.source,
        "category": signal.category,
        "score": signal.score,
        "velocity": signal.velocity,
        "url": signal.url,
        "summary": signal.summary,
    }


def _narrative(top_signal: SignalRecord | None, signals: list[SignalRecord], active_sources: int) -> str:
    if top_signal is None:
        return "No fresh signals were collected. Run a live collection to generate a daily brief."

    categories = sorted({signal.category for signal in signals})
    category_text = ", ".join(categories) if categories else "no categories"
    return (
        f"{top_signal.topic.capitalize()} is the top signal at score {top_signal.score}. "
        f"{len(signals)} signals across {active_sources} active sources cover {category_text}. "
        "Use the Act Now list first, then check job and research momentum for timing."
    )
