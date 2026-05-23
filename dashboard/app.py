from __future__ import annotations

from dataclasses import asdict, is_dataclass
import os
from typing import Any

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
                "domain_score": _domain_score(signal),
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


def _domain_score(signal: SignalRecord) -> object:
    for key in (
        "research_score",
        "funding_score",
        "hackathon_score",
        "internship_score",
        "startup_gap_score",
        "trend_score",
    ):
        if key in signal.metadata:
            return signal.metadata[key]
    return ""


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
    rows = []
    for item in items:
        if is_dataclass(item):
            rows.append(asdict(item))
        else:
            rows.append(getattr(item, "__dict__", {}))
    return pd.DataFrame(rows)


def _category_distribution_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    frame = _signals_to_frame(signals)
    return frame.groupby("category", as_index=False).size().rename(columns={"size": "signals"})


def _source_distribution_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    if not signals:
        return pd.DataFrame()
    frame = _signals_to_frame(signals)
    return frame.groupby("source", as_index=False)["score"].mean().sort_values("score", ascending=False).head(12)


def _apply_filters(signals: list[SignalRecord], filters: dict[str, Any] | None = None) -> list[SignalRecord]:
    filters = filters or {}
    categories = set(filters.get("categories") or [])
    source = str(filters.get("source") or "")
    query = str(filters.get("query") or "").strip().lower()
    min_score = int(filters.get("min_score", 0))
    filtered: list[SignalRecord] = []
    for signal in signals:
        haystack = f"{signal.topic} {signal.title} {signal.summary} {signal.source} {signal.category}".lower()
        if categories and signal.category not in categories:
            continue
        if source and signal.source != source:
            continue
        if query and query not in haystack:
            continue
        if signal.score < min_score:
            continue
        filtered.append(signal)
    return filtered


def _render_signal_explorer(signals: list[SignalRecord], filters: dict[str, Any] | None = None, key_prefix: str = "signals") -> None:
    filtered = _apply_filters(signals, filters)
    cols = st.columns(4)
    cols[0].metric("Signals in view", len(filtered))
    cols[1].metric("Avg score", f"{sum(signal.score for signal in filtered) / max(len(filtered), 1):.1f}")
    cols[2].metric("Sources", len({signal.source for signal in filtered}))
    cols[3].metric("Topics", len({signal.topic for signal in filtered}))

    if not filtered:
        st.info("No signals for this view yet. Run a live collection or adjust source settings.")
        return

    chart_cols = st.columns(2)
    category_frame = _category_distribution_frame(filtered)
    if not category_frame.empty:
        chart_cols[0].bar_chart(category_frame, x="category", y="signals")
    source_frame = _source_distribution_frame(filtered)
    if not source_frame.empty:
        chart_cols[1].bar_chart(source_frame, x="source", y="score")

    frame = _signals_to_frame(filtered)
    st.dataframe(frame, width="stretch", hide_index=True)
    st.download_button(
        "Download CSV",
        frame.to_csv(index=False).encode("utf-8"),
        file_name="internet-radar-signals.csv",
        mime="text/csv",
        key=f"download-{key_prefix}",
    )
    selected = st.selectbox("Inspect signal", [signal.title for signal in filtered], key=f"inspect-{key_prefix}")
    signal = next(item for item in filtered if item.title == selected)
    with st.expander("Signal detail", expanded=False):
        st.json(signal.model_dump(mode="json"))


def render_page(page_key: str, page_payload: dict[str, object], filters: dict[str, Any] | None = None) -> None:
    st.subheader(str(page_payload["title"]))
    st.caption(str(page_payload["description"]))

    if page_key == "profile":
        profile = dict(page_payload.get("profile", {}))
        columns = st.columns(3)
        columns[0].metric("Skills", len(profile.get("skills", [])))
        columns[1].metric("Interests", len(profile.get("interests", [])))
        columns[2].metric("Alert threshold", int(profile.get("alert_threshold", 0)))
        st.json(profile)
        personalized = list(page_payload.get("personalized_signals", []))
        if personalized:
            st.subheader("Personalized Feed")
            _render_signal_explorer(personalized, filters, key_prefix="profile-personalized")
        return

    if page_key == "radar_search":
        st.text_input("Search collected signals", value=str((filters or {}).get("query") or "browser agents"), key="radar-search-query")
        st.json(page_payload.get("query_analysis", {}))

    if page_key == "briefing":
        signal_summary = page_payload.get("signal_summary")
        if signal_summary:
            st.subheader("Signal Summary")
            st.write(getattr(signal_summary, "headline", ""))
            st.write(getattr(signal_summary, "next_action", ""))
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
        predictions = list(page_payload.get("trend_predictions", []))
        if predictions:
            st.subheader("Trend Predictions")
            st.dataframe(_objects_to_frame(predictions), width="stretch", hide_index=True)

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
        analyses = list(page_payload.get("gap_analyses", []))
        if page_key == "startup_gaps" and analyses:
            st.subheader("Gap Analysis")
            st.dataframe(_objects_to_frame(analyses), width="stretch", hide_index=True)
        validations = list(page_payload.get("idea_validations", []))
        if page_key == "startup_gaps" and validations:
            st.subheader("Idea Validation")
            st.dataframe(_objects_to_frame(validations), width="stretch", hide_index=True)
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
    _render_signal_explorer(signals, filters, key_prefix=page_key)


def render_dashboard(payload: dict[str, dict[str, object]], filters: dict[str, Any] | None = None) -> None:
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
            render_page(page.key, payload[page.key], filters=filters)


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
        st.header("Filters")
        categories = st.multiselect(
            "Categories",
            ["code", "social", "news", "jobs", "hackathons", "research", "finance", "search", "app_stores"],
            default=[],
        )
        min_score = st.slider("Minimum score", min_value=0, max_value=100, value=0, step=5)
        query = st.text_input("Search text", value="")
        source_options = sorted({source.name for source in SOURCE_REGISTRY})
        source = st.selectbox("Source", [""] + source_options, index=0)

    render_dashboard(
        load_payload(use_live_network=use_live),
        filters={"categories": categories, "min_score": min_score, "query": query, "source": source},
    )


if __name__ == "__main__":
    main()
