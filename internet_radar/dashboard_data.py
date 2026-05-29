from __future__ import annotations

from collections import defaultdict
from typing import Any

from internet_radar.alerts.alert_manager import build_alerts
from internet_radar.brain.briefing_writer import write_daily_briefing
from internet_radar.brain.classifier import classify_signals
from internet_radar.brain.gap_analyzer import analyze_gaps
from internet_radar.brain.idea_validator import validate_ideas
from internet_radar.brain.llm_router import LLMRouter
from internet_radar.brain.relevance_scorer import rank_for_profile
from internet_radar.brain.skill_recommender import recommend_skills
from internet_radar.brain.summarizer import summarize_signals
from internet_radar.brain.trend_predictor import predict_trends
from internet_radar.scoring.funding_scorer import FundingScorer
from internet_radar.scoring.hackathon_scorer import HackathonScorer
from internet_radar.scoring.internship_scorer import InternshipScorer
from internet_radar.scoring.research_signal_scorer import ResearchSignalScorer
from internet_radar.scoring.startup_gap_scorer import StartupGapScorer
from internet_radar.scoring.trend_scorer import TrendScorer
from internet_radar.search.radar_search import analyze_query
from internet_radar.signals.academic_signal import build_academic_signals
from internet_radar.signals.crowd_predictor import predict_crowd
from internet_radar.signals.cross_source_multiplier import build_source_agreements
from internet_radar.signals.funding_signal import build_funding_signals
from internet_radar.signals.gap_finder import find_startup_gaps
from internet_radar.signals.sentiment_pipeline import enrich_signals_with_sentiment, summarize_sentiment
from internet_radar.signals.trend_correlator import correlate_trends
from internet_radar.storage.models import HistoricalTrend, PageDefinition, SignalRecord, UserProfile
from internet_radar.storage.vector_store import build_semantic_clusters


PAGE_DEFINITIONS = [
    PageDefinition(key="briefing", title="Morning Intelligence Briefing", category="all", description="Daily ranked signal summary."),
    PageDefinition(key="github_radar", title="GitHub Radar", category="code", description="Repository and package velocity."),
    PageDefinition(key="hackathon_radar", title="Hackathon Radar", category="hackathons", description="Hackathon opportunity scoring."),
    PageDefinition(key="startup_gaps", title="Startup Gap Finder", category="mixed", description="Pain signals and product gaps."),
    PageDefinition(key="trend_velocity", title="Multi-Source Trend Velocity", category="all", description="Cross-source trend momentum."),
    PageDefinition(key="research_radar", title="Research Radar", category="research", description="Academic momentum and future demand."),
    PageDefinition(key="funding_radar", title="Funding Radar", category="finance", description="Money flow and market validation."),
    PageDefinition(key="skill_radar", title="Skill Radar", category="mixed", description="Skills heating up across jobs and code."),
    PageDefinition(key="community_pulse", title="Community Pulse", category="social", description="Developer discussion and sentiment."),
    PageDefinition(key="app_store_pain", title="App Store Pain Miner", category="app_stores", description="Review pain and competitor weakness."),
    PageDefinition(key="radar_search", title="Radar Search", category="all", description="Search across collected signals."),
    PageDefinition(key="profile", title="Your Profile", category="profile", description="Interests, goals, and thresholds."),
]


def build_dashboard_payload(
    signals: list[SignalRecord],
    active_sources: int = 0,
    llm_status: str = "unknown",
    profile: UserProfile | None = None,
    generated_at: object | None = None,
    collection_duration_seconds: float = 0.0,
    collection_mode: str = "sample",
    loaded_from_cache: bool = False,
    source_health: dict[str, str] | None = None,
    source_counts: dict[str, int] | None = None,
    source_durations_seconds: dict[str, float] | None = None,
    historical_trends: list[HistoricalTrend] | None = None,
    analysis_artifacts: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    by_category: dict[str, list[SignalRecord]] = defaultdict(list)
    profile = profile or UserProfile()
    enrich_signals_with_sentiment(signals)
    enrich_domain_scores(signals, profile)
    for signal in sorted(signals, key=lambda item: item.score, reverse=True):
        by_category[signal.category].append(signal)

    all_signals = sorted(signals, key=lambda item: item.score, reverse=True)
    router = LLMRouter()
    personalized_signals = rank_for_profile(all_signals, profile, limit=10)
    alerts = build_alerts(all_signals, profile)
    suggested_queries = profile.interests[:5] or [signal.topic for signal in all_signals[:5]]
    query_analysis = {
        query: analyze_query(all_signals, query, profile=profile, include_deep_dive=True, include_semantic=True)
        for query in suggested_queries
    }
    gap_clusters = find_startup_gaps(all_signals)
    semantic_clusters = build_semantic_clusters(all_signals)
    source_agreements = build_source_agreements(all_signals)
    trend_correlations = correlate_trends(all_signals)
    academic_signals = build_academic_signals(all_signals)
    funding_signals = build_funding_signals(all_signals)
    crowd_predictions = [
        predict_crowd({"title": signal.title, **signal.metadata})
        for signal in all_signals
        if signal.category == "hackathons"
    ]
    signal_summary = summarize_signals(all_signals, router=router)
    classifications = classify_signals(all_signals, router=router, allow_network=False)
    gap_analyses = analyze_gaps(all_signals, router=router)
    trend_predictions = predict_trends(all_signals, router=router)
    idea_validations = validate_ideas(
        [analysis.startup_ideas[0].idea for analysis in gap_analyses if analysis.startup_ideas],
        all_signals,
        profile=profile,
        router=router,
    )
    daily_briefing = write_daily_briefing(all_signals, active_sources=active_sources, llm_status=llm_status)
    skill_recommendations = recommend_skills(all_signals, profile=profile)
    historical_trends = historical_trends or []
    analysis_artifacts = analysis_artifacts or {}
    signal_summary = _artifact_value(analysis_artifacts, "signal_summary", signal_summary)
    classifications = _artifact_value(analysis_artifacts, "classifications", classifications)
    gap_analyses = _artifact_value(analysis_artifacts, "gap_analyses", gap_analyses)
    trend_predictions = _artifact_value(analysis_artifacts, "trend_predictions", trend_predictions)
    idea_validations = _artifact_value(analysis_artifacts, "idea_validations", idea_validations)
    daily_briefing = _artifact_value(analysis_artifacts, "daily_briefing", daily_briefing)
    llm_generated_insight = _artifact_value(analysis_artifacts, "llm_generated_insight", {})
    collection = {
        "generated_at": generated_at,
        "duration_seconds": collection_duration_seconds,
        "mode": collection_mode,
        "loaded_from_cache": loaded_from_cache,
    }
    payload: dict[str, dict[str, Any]] = {}
    for page in PAGE_DEFINITIONS:
        if page.category == "all":
            page_signals = all_signals
        elif page.key == "startup_gaps":
            page_signals = [signal for signal in all_signals if signal.category in {"social", "news", "app_stores"}]
        elif page.key == "skill_radar":
            page_signals = [signal for signal in all_signals if signal.category in {"jobs", "code", "research"}]
        elif page.category == "profile":
            page_signals = []
        else:
            page_signals = by_category[str(page.category)]

        payload[page.key] = {
            "title": page.title,
            "description": page.description,
            "signals": page_signals,
            "active_sources": active_sources,
            "signals_24h": len(all_signals),
            "llm_status": llm_status,
            "collection": collection,
            "source_health": source_health or {},
            "source_counts": source_counts or {},
            "source_durations_seconds": source_durations_seconds or {},
            "historical_trends": historical_trends,
            "analysis_artifacts": analysis_artifacts,
            "personalized_signals": personalized_signals,
            "alerts": alerts,
            "daily_briefing": daily_briefing,
            "llm_generated_insight": llm_generated_insight,
            "gap_clusters": gap_clusters,
            "pain_clusters": gap_clusters,
            "semantic_clusters": semantic_clusters,
            "source_agreements": source_agreements,
            "trend_correlations": trend_correlations,
            "academic_signals": academic_signals,
            "funding_signals": funding_signals,
            "crowd_predictions": crowd_predictions,
            "signal_summary": signal_summary,
            "classifications": classifications,
            "gap_analyses": gap_analyses,
            "trend_predictions": trend_predictions,
            "idea_validations": idea_validations,
            "skill_recommendations": skill_recommendations,
            "sentiment_summary": summarize_sentiment(page_signals),
            "profile": profile.model_dump(),
            "suggested_queries": suggested_queries,
            "query_analysis": query_analysis,
        }
    return payload


def _artifact_value(analysis_artifacts: dict[str, Any], key: str, fallback: Any) -> Any:
    return analysis_artifacts[key] if key in analysis_artifacts else fallback


def enrich_domain_scores(signals: list[SignalRecord], profile: UserProfile | None = None) -> None:
    profile = profile or UserProfile()
    profile_data = profile.model_dump()
    research_scorer = ResearchSignalScorer()
    funding_scorer = FundingScorer()
    hackathon_scorer = HackathonScorer()
    internship_scorer = InternshipScorer()
    startup_gap_scorer = StartupGapScorer()
    trend_scorer = TrendScorer()
    for signal in signals:
        if signal.category == "research":
            result = research_scorer.score({"topic": signal.topic, **signal.metadata})
            signal.metadata["research_score"] = result.score
            signal.metadata["research_components"] = result.components
            signal.metadata["recommended_skill"] = result.recommended_skill
            signal.metadata["industry_lag_months"] = result.industry_lag_months
        elif signal.category == "finance":
            result = funding_scorer.score({"sector": signal.topic, **signal.metadata})
            signal.metadata["funding_score"] = result.score
            signal.metadata["funding_components"] = result.components
            signal.metadata["market_validation"] = result.market_validation
        elif signal.category == "hackathons":
            result = hackathon_scorer.score({"theme": signal.topic, "title": signal.title, **signal.metadata}, profile_data)
            signal.metadata["hackathon_score"] = result.score
            signal.metadata["hackathon_components"] = result.components
            signal.metadata["hackathon_recommendation"] = result.recommendation
        elif signal.category == "jobs":
            result = internship_scorer.score(
                {"description": f"{signal.topic} {signal.title} {signal.summary}", **signal.metadata},
                profile_data,
            )
            signal.metadata["internship_score"] = result.score
            signal.metadata["internship_components"] = result.components
            signal.metadata["internship_recommendation"] = result.recommendation
        elif signal.category in {"social", "news", "app_stores"}:
            result = startup_gap_scorer.score(
                {
                    "complaint_count": signal.metadata.get("complaint_count", 10 if signal.metadata.get("frustration_score", 0) >= 45 else 0),
                    "market_score": signal.metadata.get("market_score", 0.5),
                    "competition_score": signal.metadata.get("competition_score", 0.5),
                    "feasibility_score": signal.metadata.get("feasibility_score", 0.5),
                    "trend_phase": signal.metadata.get("trend_phase", "EMERGING"),
                }
            )
            signal.metadata["startup_gap_score"] = result.score
            signal.metadata["startup_gap_components"] = result.components
            signal.metadata["startup_gap_recommendation"] = result.recommendation
        if signal.category in {"code", "search", "news"} or {"confirming_sources", "phase", "funding_detected"} & signal.metadata.keys():
            result = trend_scorer.score(
                {
                    "velocity_score": signal.metadata.get("velocity_score", signal.velocity),
                    "confirming_sources": signal.metadata.get("confirming_sources", 1),
                    "phase": signal.metadata.get("phase", "EMERGING"),
                    "funding_detected": signal.metadata.get("funding_detected", False),
                }
            )
            signal.metadata["trend_score"] = result.score
            signal.metadata["trend_components"] = result.components
            signal.metadata["trend_phase"] = result.phase
