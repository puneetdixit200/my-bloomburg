from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
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
    }
    return _to_plain(artifacts)


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
