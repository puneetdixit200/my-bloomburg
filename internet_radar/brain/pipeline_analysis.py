from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
import os
from typing import Any

from pydantic import BaseModel

from internet_radar.brain.briefing_writer import write_daily_briefing
from internet_radar.brain.classifier import classify_signals
from internet_radar.brain.gap_analyzer import analyze_gaps
from internet_radar.brain.idea_validator import validate_ideas
from internet_radar.brain.llm_router import LLMRouter
from internet_radar.brain.summarizer import summarize_signals
from internet_radar.brain.trend_predictor import predict_trend, predict_trends
from internet_radar.storage.models import SignalRecord, UserProfile


def build_analysis_artifacts(
    signals: list[SignalRecord],
    *,
    active_sources: int,
    llm_status: str,
    profile: UserProfile | None = None,
    router: LLMRouter | None = None,
) -> dict[str, Any]:
    profile = profile or UserProfile()
    router = router or LLMRouter()
    gap_analyses = analyze_gaps(signals, router=router)
    idea_inputs = [analysis.startup_ideas[0].idea for analysis in gap_analyses if analysis.startup_ideas]
    trend_predictions = predict_trends(signals, router=router)
    if not trend_predictions and signals:
        trend_predictions = [predict_trend(signals[0].topic, signals, router=router)]
    artifacts = {
        "analysis_route": llm_status,
        "signal_summary": summarize_signals(signals, router=router),
        "classifications": classify_signals(signals, router=router, allow_network=False),
        "gap_analyses": gap_analyses,
        "trend_predictions": trend_predictions,
        "idea_validations": validate_ideas(idea_inputs, signals, profile=profile, router=router),
        "daily_briefing": write_daily_briefing(signals, active_sources=active_sources, llm_status=llm_status),
        "llm_generated_insight": build_llm_generated_insight(
            signals,
            active_sources=active_sources,
            router=router,
            allow_network=os.getenv("INTERNET_RADAR_ENABLE_LLM_ANALYSIS", "0") == "1",
        ),
    }
    return _to_plain(artifacts)


def build_llm_generated_insight(
    signals: list[SignalRecord],
    *,
    active_sources: int,
    router: LLMRouter,
    allow_network: bool,
) -> dict[str, Any]:
    prompt = _insight_prompt(signals, active_sources=active_sources)
    generate_json = getattr(router, "generate_json", None)
    if callable(generate_json):
        route, result = generate_json(
            "daily_briefing",
            prompt,
            content_length=len(prompt),
            allow_network=allow_network,
        )
    else:
        route = router.route("daily_briefing", len(prompt))
        result = {}
    return _normalize_insight(result, route=route, signals=signals, active_sources=active_sources, enabled=allow_network)


def _insight_prompt(signals: list[SignalRecord], *, active_sources: int) -> str:
    top = sorted(signals, key=lambda signal: (signal.score, signal.velocity), reverse=True)[:10]
    signal_lines = [
        (
            f"- title={signal.title!r}; topic={signal.topic!r}; source={signal.source!r}; "
            f"category={signal.category!r}; score={signal.score}; velocity={signal.velocity}; summary={signal.summary!r}"
        )
        for signal in top
    ]
    return "\n".join(
        [
            "You are Internet Radar. Return ONLY valid JSON.",
            "Keys: headline string, narrative string, opportunities list of strings, risks list of strings, actions list of strings, confidence integer 0-100.",
            f"Active sources: {active_sources}.",
            "Signals:",
            *signal_lines,
        ]
    )


def _normalize_insight(
    result: dict[str, Any],
    *,
    route: Any,
    signals: list[SignalRecord],
    active_sources: int,
    enabled: bool,
) -> dict[str, Any]:
    top = sorted(signals, key=lambda signal: (signal.score, signal.velocity), reverse=True)
    top_signal = top[0] if top else None
    status = "generated" if result else ("disabled" if not enabled else "fallback")
    headline = _text(result.get("headline")) or (f"{top_signal.topic} is the strongest live signal" if top_signal else "No live signals yet")
    narrative = _text(result.get("narrative")) or (
        f"{len(top)} signals across {active_sources} active sources are available for morning review."
        if top
        else "Run a live collection to generate an LLM-backed operational brief."
    )
    return {
        "status": status,
        "provider": getattr(route, "provider", "unknown"),
        "model": getattr(route, "model", "unknown"),
        "headline": headline,
        "narrative": narrative,
        "opportunities": _string_list(result.get("opportunities")) or _fallback_opportunities(top),
        "risks": _string_list(result.get("risks")) or _fallback_risks(top),
        "actions": _string_list(result.get("actions")) or _fallback_actions(top),
        "confidence": _confidence(result.get("confidence"), generated=bool(result)),
    }


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()][:5]


def _confidence(value: object, *, generated: bool) -> int:
    try:
        confidence = int(float(str(value).strip().rstrip("%")))
    except (TypeError, ValueError):
        confidence = 75 if generated else 45
    return max(0, min(confidence, 100))


def _fallback_opportunities(signals: list[SignalRecord]) -> list[str]:
    return [f"Investigate {signal.topic} from {signal.source}" for signal in signals[:3]] or ["Collect more live signals"]


def _fallback_risks(signals: list[SignalRecord]) -> list[str]:
    if len({signal.source for signal in signals[:10]}) < 3:
        return ["Needs broader source confirmation"]
    return ["Validate that high-scoring signals reflect real user demand"]


def _fallback_actions(signals: list[SignalRecord]) -> list[str]:
    return [f"Open and inspect: {signal.title}" for signal in signals[:3]] or ["Run a live collection"]


def _to_plain(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain(item) for item in value]
    if isinstance(value, tuple):
        return [_to_plain(item) for item in value]
    return value
