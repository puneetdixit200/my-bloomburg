from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from internet_radar.config.settings import load_user_profile
from internet_radar.dashboard_data import PAGE_DEFINITIONS, build_dashboard_payload
from internet_radar.pipeline import run_radar_once
from internet_radar.sources.registry import SOURCE_REGISTRY, enabled_sources
from internet_radar.storage.models import SignalRecord


def _signals_to_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "score": signal.score,
                "domain_score": signal.metadata.get("research_score", signal.metadata.get("funding_score", "")),
                "relevance": signal.metadata.get("relevance_score", ""),
                "topic": signal.topic,
                "title": signal.title,
                "source": signal.source,
                "category": signal.category,
                "url": signal.url,
            }
            for signal in signals
        ]
    )


def _gaps_to_frame(gaps: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "score": getattr(gap, "score", 0),
                "pain_level": getattr(gap, "pain_level", 0),
                "complaints": getattr(gap, "complaint_count", 0),
                "problem": getattr(gap, "problem", ""),
                "sources": ", ".join(getattr(gap, "sources", [])),
                "best_quote": getattr(gap, "best_quote", ""),
                "startup_idea": getattr(gap, "startup_idea", ""),
            }
            for gap in gaps
        ]
    )


def _sentiment_to_frame(summary: dict[str, int]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"sentiment": label, "signals": int(summary.get(label, 0))} for label in ["positive", "neutral", "negative"]]
    )


def _semantic_clusters_to_frame(clusters: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "label": getattr(cluster, "label", ""),
                "signals": getattr(cluster, "size", 0),
                "sources": ", ".join(getattr(cluster, "sources", [])),
                "keywords": ", ".join(getattr(cluster, "keywords", [])),
            }
            for cluster in clusters
        ]
    )


def _skill_recommendations_to_frame(recommendations: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "score": getattr(recommendation, "score", 0),
                "skill": getattr(recommendation, "skill", ""),
                "signals": getattr(recommendation, "demand_signals", 0),
                "sources": ", ".join(getattr(recommendation, "sources", [])),
                "topics": ", ".join(getattr(recommendation, "topics", [])),
                "next_step": (getattr(recommendation, "learning_path", []) or [""])[0],
            }
            for recommendation in recommendations
        ]
    )


def _source_agreements_to_frame(agreements: list[object]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "score": getattr(agreement, "score", 0),
                "topic": getattr(agreement, "topic", ""),
                "verdict": getattr(agreement, "verdict", ""),
                "sources": f"{getattr(agreement, 'source_count', 0)}/{getattr(agreement, 'known_source_count', 0)}",
                "multiplier": getattr(agreement, "multiplier", 1.0),
                "source_list": ", ".join(getattr(agreement, "sources", [])),
            }
            for agreement in agreements
        ]
    )


def _objects_to_frame(items: list[object]) -> pd.DataFrame:
    return pd.DataFrame([getattr(item, "__dict__", {}) for item in items])


def render_page(page_key: str, page_payload: dict[str, object]) -> None:
    st.subheader(str(page_payload["title"]))
    st.caption(str(page_payload["description"]))

    if page_key == "profile":
        profile = dict(page_payload.get("profile", {}))
        st.json(profile)
        personalized = list(page_payload.get("personalized_signals", []))
        if personalized:
            st.subheader("Personalized Feed")
            st.dataframe(_signals_to_frame(personalized), width="stretch", hide_index=True)
        return

    if page_key == "radar_search":
        st.write("Suggested queries")
        st.json(page_payload.get("query_analysis", {}))

    if page_key == "briefing":
        daily_briefing = page_payload.get("daily_briefing", {})
        if isinstance(daily_briefing, dict) and daily_briefing:
            st.subheader("Daily Brief")
            st.write(str(daily_briefing.get("narrative", "")))
        alerts = list(page_payload.get("alerts", []))
        if alerts:
            st.subheader("Act Now")
            for alert in alerts[:5]:
                st.markdown(f"**{alert.title}**")
                st.caption(f"{alert.kind} | score {alert.score} | channels: {', '.join(alert.channels)}")
                st.code(alert.body)

    if page_key == "skill_radar":
        recommendations = list(page_payload.get("skill_recommendations", []))
        if recommendations:
            st.subheader("Learning Path")
            st.dataframe(_skill_recommendations_to_frame(recommendations), width="stretch", hide_index=True)

    if page_key == "trend_velocity":
        agreements = list(page_payload.get("source_agreements", []))
        if agreements:
            st.subheader("Source Agreement")
            st.dataframe(_source_agreements_to_frame(agreements), width="stretch", hide_index=True)
        correlations = list(page_payload.get("trend_correlations", []))
        if correlations:
            st.subheader("Trend Correlations")
            st.dataframe(_objects_to_frame(correlations), width="stretch", hide_index=True)

    if page_key == "hackathon_radar":
        predictions = list(page_payload.get("crowd_predictions", []))
        if predictions:
            st.subheader("Crowd Prediction")
            st.dataframe(_objects_to_frame(predictions), width="stretch", hide_index=True)

    if page_key == "research_radar":
        academic_signals = list(page_payload.get("academic_signals", []))
        if academic_signals:
            st.subheader("Academic Momentum")
            st.dataframe(_objects_to_frame(academic_signals), width="stretch", hide_index=True)

    if page_key == "funding_radar":
        funding_signals = list(page_payload.get("funding_signals", []))
        if funding_signals:
            st.subheader("Funding Validation")
            st.dataframe(_objects_to_frame(funding_signals), width="stretch", hide_index=True)

    if page_key in {"startup_gaps", "app_store_pain"}:
        gap_key = "pain_clusters" if page_key == "app_store_pain" else "gap_clusters"
        gaps = list(page_payload.get(gap_key, []))
        if gaps:
            st.subheader("Pain Clusters")
            st.dataframe(_gaps_to_frame(gaps), width="stretch", hide_index=True)
        semantic_clusters = list(page_payload.get("semantic_clusters", []))
        if semantic_clusters:
            st.subheader("Semantic Clusters")
            st.dataframe(_semantic_clusters_to_frame(semantic_clusters), width="stretch", hide_index=True)

    if page_key == "community_pulse":
        summary = page_payload.get("sentiment_summary", {})
        if isinstance(summary, dict) and any(int(value) for value in summary.values()):
            st.subheader("Sentiment Summary")
            st.dataframe(_sentiment_to_frame(summary), width="stretch", hide_index=True)

    signals = list(page_payload.get("signals", []))
    if signals:
        st.dataframe(_signals_to_frame(signals), width="stretch", hide_index=True)
    else:
        st.info("No signals for this view yet. Run a live collection or adjust source settings.")


def render_dashboard(payload: dict[str, dict[str, object]]) -> None:
    top = payload["briefing"]
    cols = st.columns(4)
    cols[0].metric("Active sources", int(top["active_sources"]))
    cols[1].metric("Signals", int(top["signals_24h"]))
    cols[2].metric("Registered sources", len(SOURCE_REGISTRY))
    cols[3].metric("Enabled by default", len(enabled_sources()))

    st.write(f"LLM route: `{top['llm_status']}`")
    tabs = st.tabs([page.title for page in PAGE_DEFINITIONS])
    for tab, page in zip(tabs, PAGE_DEFINITIONS, strict=True):
        with tab:
            render_page(page.key, payload[page.key])


def render_page_entry(page_key: str) -> None:
    page = next((definition for definition in PAGE_DEFINITIONS if definition.key == page_key), PAGE_DEFINITIONS[0])
    st.set_page_config(page_title=f"Internet Radar v2 - {page.title}", layout="wide")
    st.title(page.title)
    payload = load_payload(use_live_network=os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1")
    render_page(page.key, payload[page.key])


def load_payload(use_live_network: bool = False) -> dict[str, dict[str, object]]:
    briefing = run_radar_once(use_live_network=use_live_network)
    profile = load_user_profile()
    return build_dashboard_payload(
        briefing.top_signals,
        active_sources=briefing.active_sources,
        llm_status=briefing.llm_status,
        profile=profile,
    )


def main() -> None:
    st.set_page_config(page_title="Internet Radar v2", layout="wide")
    st.title("Internet Radar v2")
    st.caption("Local-first signal intelligence across code, social, news, jobs, research, finance, search, and app stores.")

    with st.sidebar:
        st.header("Collection")
        default_live = os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1"
        use_live = st.toggle("Use live network collectors", value=default_live)
        st.caption("Off uses deterministic sample signals. On calls no-key public APIs and falls back on errors.")

    render_dashboard(load_payload(use_live_network=use_live))


if __name__ == "__main__":
    main()
