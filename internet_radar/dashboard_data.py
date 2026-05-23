from __future__ import annotations

from collections import defaultdict
from typing import Any

from internet_radar.alerts.alert_manager import build_alerts
from internet_radar.brain.briefing_writer import write_daily_briefing
from internet_radar.brain.relevance_scorer import rank_for_profile
from internet_radar.brain.skill_recommender import recommend_skills
from internet_radar.scoring.funding_scorer import FundingScorer
from internet_radar.scoring.research_signal_scorer import ResearchSignalScorer
from internet_radar.search.radar_search import analyze_query
from internet_radar.signals.academic_signal import build_academic_signals
from internet_radar.signals.crowd_predictor import predict_crowd
from internet_radar.signals.cross_source_multiplier import build_source_agreements
from internet_radar.signals.funding_signal import build_funding_signals
from internet_radar.signals.gap_finder import find_startup_gaps
from internet_radar.signals.sentiment_pipeline import enrich_signals_with_sentiment, summarize_sentiment
from internet_radar.signals.trend_correlator import correlate_trends
from internet_radar.storage.models import PageDefinition, SignalRecord, UserProfile
from internet_radar.storage.vector_store import build_semantic_clusters


PAGE_DEFINITIONS = [
    PageDefinition(key="briefing", title="Morning Intelligence Briefing", category="all", description="Daily ranked signal summary."),
    PageDefinition(key="github_radar", title="GitHub Radar", category="code", description="Repository and package velocity."),
    PageDefinition(key="hackathon_radar", title="Hackathon Radar", category="hackathons", description="Hackathon opportunity scoring."),
    PageDefinition(key="internship_radar", title="Internship Radar", category="jobs", description="Fresh jobs and skill match."),
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
) -> dict[str, dict[str, Any]]:
    by_category: dict[str, list[SignalRecord]] = defaultdict(list)
    enrich_signals_with_sentiment(signals)
    enrich_domain_scores(signals)
    for signal in sorted(signals, key=lambda item: item.score, reverse=True):
        by_category[signal.category].append(signal)

    all_signals = sorted(signals, key=lambda item: item.score, reverse=True)
    profile = profile or UserProfile()
    personalized_signals = rank_for_profile(all_signals, profile, limit=10)
    alerts = build_alerts(all_signals, profile)
    suggested_queries = profile.interests[:5] or [signal.topic for signal in all_signals[:5]]
    query_analysis = {
        query: analyze_query(all_signals, query, profile=profile, include_deep_dive=True)
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
    daily_briefing = write_daily_briefing(all_signals, active_sources=active_sources, llm_status=llm_status)
    skill_recommendations = recommend_skills(all_signals, profile=profile)
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
            "personalized_signals": personalized_signals,
            "alerts": alerts,
            "daily_briefing": daily_briefing,
            "gap_clusters": gap_clusters,
            "pain_clusters": gap_clusters,
            "semantic_clusters": semantic_clusters,
            "source_agreements": source_agreements,
            "trend_correlations": trend_correlations,
            "academic_signals": academic_signals,
            "funding_signals": funding_signals,
            "crowd_predictions": crowd_predictions,
            "skill_recommendations": skill_recommendations,
            "sentiment_summary": summarize_sentiment(page_signals),
            "profile": profile.model_dump(),
            "suggested_queries": suggested_queries,
            "query_analysis": query_analysis,
        }
    return payload


def enrich_domain_scores(signals: list[SignalRecord]) -> None:
    research_scorer = ResearchSignalScorer()
    funding_scorer = FundingScorer()
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
