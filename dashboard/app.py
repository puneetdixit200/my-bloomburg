from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
import os
from threading import Thread
from typing import Any

import pandas as pd
import streamlit as st

from internet_radar.alerts.dispatcher import alert_readiness
from internet_radar.config.settings import load_user_profile
from internet_radar.dashboard_data import PAGE_DEFINITIONS, build_dashboard_payload
from internet_radar.pipeline import run_radar_once
from internet_radar.sources.registry import SOURCE_REGISTRY, enabled_sources
from internet_radar.storage.models import BriefingPayload, SignalRecord
from internet_radar.storage.payload_cache import load_briefing_payload, payload_cache_age_seconds, save_briefing_payload


CATEGORIES = ["code", "social", "news", "jobs", "hackathons", "research", "finance", "search", "app_stores"]
_BACKGROUND_REFRESH_RUNNING = False


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


def _source_health_frame(page_payload: dict[str, object], category: str | None = None) -> pd.DataFrame:
    health = dict(page_payload.get("source_health", {}))
    counts = dict(page_payload.get("source_counts", {}))
    durations = dict(page_payload.get("source_durations_seconds", {}))
    rows = []
    for source, status in sorted(health.items()):
        source_category = _source_category(source)
        if category and category != "all" and source_category != category:
            continue
        rows.append(
            {
                "source": source,
                "category": source_category or "",
                "status": status,
                "signals": int(counts.get(source, 0) or 0),
                "seconds": float(durations.get(source, 0.0) or 0.0),
                "mode": _status_mode(str(status)),
            }
        )
    return pd.DataFrame(rows)


def _free_only_guardrails_frame(free_only: bool | None = None) -> pd.DataFrame:
    if free_only is None:
        free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
    status = "disabled" if free_only else "credential-gated"
    reason = (
        "Disabled by free-only mode so paid network calls stay off."
        if free_only
        else "Requires explicit credentials before any network call is attempted."
    )
    return pd.DataFrame(
        [
            {"integration": "Brave Search API", "surface": "collector", "status": status, "reason": reason},
            {"integration": "Crunchbase API", "surface": "collector", "status": status, "reason": reason},
            {"integration": "Mailgun Email", "surface": "alerts", "status": status, "reason": reason},
        ]
    )


def _alert_readiness_frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"channel": item.channel, "ready": item.ready, "detail": item.detail}
            for item in alert_readiness()
        ]
    )


def _source_category(source_name: str) -> str | None:
    for source in SOURCE_REGISTRY:
        if source.name == source_name:
            return str(source.category)
    return None


def _status_mode(status: str) -> str:
    if status.startswith(("live", "ok")):
        return "live"
    if status.startswith("fallback"):
        return "fallback"
    if status.startswith("error"):
        return "error"
    return "unknown"


def _signal_preview_frame(signals: list[SignalRecord], limit: int = 10) -> pd.DataFrame:
    columns = ["score", "title", "source", "category", "url"]
    frame = _signals_to_frame(_balanced_signals(signals, limit=limit, max_per_source=2))
    if frame.empty:
        return pd.DataFrame(columns=columns)
    return frame[columns]


def _signal_display_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return _signals_to_frame(_balanced_signals(signals))


def _balanced_signals(
    signals: list[SignalRecord],
    *,
    limit: int | None = None,
    max_per_source: int | None = None,
) -> list[SignalRecord]:
    buckets: dict[str, list[SignalRecord]] = {}
    source_order: list[str] = []
    for signal in signals:
        if signal.source not in buckets:
            buckets[signal.source] = []
            source_order.append(signal.source)
        buckets[signal.source].append(signal)

    balanced: list[SignalRecord] = []
    source_counts: dict[str, int] = {source: 0 for source in source_order}
    cap_released = False
    while any(buckets.values()):
        added_this_round = False
        for source in source_order:
            if limit is not None and len(balanced) >= limit:
                return balanced
            if not buckets[source]:
                continue
            if max_per_source is not None and source_counts[source] >= max_per_source:
                continue
            balanced.append(buckets[source].pop(0))
            source_counts[source] += 1
            added_this_round = True
        if not added_this_round:
            if max_per_source is not None and not cap_released:
                max_per_source = None
                cap_released = True
                continue
            break
    return balanced


def _signal_table_column_config() -> dict[str, object]:
    return {"url": st.column_config.LinkColumn("url", display_text="Open")}


def _project_signals(signals: list[SignalRecord]) -> list[SignalRecord]:
    project_sources = {"GitHub Search", "GitHub Trending", "GitLab Explore", "MCP Servers Directory"}
    return [signal for signal in signals if signal.source in project_sources and _is_project_url(signal.url)]


def _projects_to_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "score": signal.score,
                "project": _project_name(signal),
                "source": signal.source,
                "stars": signal.metadata.get("stars", ""),
                "language": signal.metadata.get("language", ""),
                "summary": signal.summary,
                "url": signal.url,
            }
            for signal in signals
        ]
    )


def _project_name(signal: SignalRecord) -> str:
    title = signal.title.removesuffix(" is trending on GitHub")
    return title if "/" in title else signal.topic or title


def _project_action(signal: SignalRecord) -> str:
    if signal.score >= 90:
        return "Watch now, inspect the README, and clone if it overlaps your interests."
    if signal.score >= 75:
        return "Track this project and compare it with adjacent tools."
    return "Keep as background context unless it appears in more sources."


def _is_project_url(url: str) -> bool:
    if not url:
        return False
    if "github.com/search" in url:
        return False
    return any(host in url for host in ("github.com/", "gitlab.com/"))


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
        elif hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        else:
            rows.append(getattr(item, "__dict__", {}))
    return pd.DataFrame(rows)


def _build_markdown_report(payload: dict[str, dict[str, object]]) -> str:
    top = payload["briefing"]
    collection = dict(top.get("collection", {}))
    lines = [
        "# Internet Radar Daily Report",
        "",
        f"- Generated: {collection.get('generated_at') or 'unknown'}",
        f"- Mode: {collection.get('mode', 'unknown')}",
        f"- Active sources: {top.get('active_sources', 0)}",
        f"- Signals: {top.get('signals_24h', 0)}",
        f"- LLM route: {top.get('llm_status', 'unknown')}",
        "",
    ]
    sections = [
        ("Top Signals", payload["briefing"].get("signals", [])[:10]),
        ("Projects", _project_signals(list(payload["github_radar"].get("signals", [])))[:10]),
        ("Startup Gaps", payload["startup_gaps"].get("signals", [])[:10]),
        ("Skills", payload["skill_radar"].get("signals", [])[:10]),
        ("Research", payload["research_radar"].get("signals", [])[:10]),
    ]
    for title, signals in sections:
        lines.extend([f"## {title}", ""])
        if not signals:
            lines.append("- No signals in this section.")
        for signal in signals:
            lines.append(f"- [{signal.score}] {signal.title} ({signal.source}) {signal.url}".rstrip())
        lines.append("")
    return "\n".join(lines)


def _render_project_details(projects: list[SignalRecord]) -> None:
    if not projects:
        return
    labels = [_project_name(signal) for signal in projects]
    selected = st.selectbox("Inspect project", labels, key="inspect-project")
    signal = projects[labels.index(selected)]
    with st.expander("Project detail", expanded=True):
        cols = st.columns(4)
        cols[0].metric("Score", signal.score)
        cols[1].metric("Stars", signal.metadata.get("stars", ""))
        cols[2].metric("Language", signal.metadata.get("language", "") or "unknown")
        cols[3].metric("Source", signal.source)
        st.write(signal.summary or signal.title)
        st.write(f"Suggested action: {_project_action(signal)}")
        if signal.url:
            st.markdown(f"[Open project]({signal.url})")


def _render_startup_idea_cards(page_payload: dict[str, object]) -> None:
    analyses = list(page_payload.get("gap_analyses", []))
    gaps = list(page_payload.get("gap_clusters", []))
    if not analyses and not gaps:
        return
    st.subheader("Startup Idea Cards")
    for index, analysis in enumerate(analyses[:5], start=1):
        ideas = list(getattr(analysis, "startup_ideas", []))
        patterns = list(getattr(analysis, "patterns", []))
        idea = ideas[0] if ideas else None
        pattern = patterns[0] if patterns else None
        title = getattr(idea, "idea", None) or getattr(analysis, "topic", f"Idea {index}")
        with st.expander(f"{index}. {title}", expanded=index == 1):
            if pattern:
                st.write(f"Problem: {getattr(pattern, 'problem', '')}")
                st.write(f"Evidence: {getattr(pattern, 'representative_quote', '')}")
                cols = st.columns(3)
                cols[0].metric("Complaints", getattr(pattern, "complaints", 0))
                cols[1].metric("Pain", getattr(pattern, "pain_level", 0))
                cols[2].metric("Score", getattr(idea, "score", 0) if idea else 0)
            if idea:
                st.write(f"Who pays / market: {getattr(idea, 'market_size', '')}")
                st.write(f"Competition: {getattr(idea, 'competition_level', '')}")
                st.write(f"MVP difficulty: {getattr(idea, 'technical_difficulty', '')}")
            st.write(f"Next step: {getattr(analysis, 'recommended_action', '')}")
    if not analyses:
        for index, gap in enumerate(gaps[:5], start=1):
            with st.expander(f"{index}. {getattr(gap, 'startup_idea', 'Startup idea')}", expanded=index == 1):
                st.write(f"Problem: {getattr(gap, 'problem', '')}")
                st.write(f"Evidence: {getattr(gap, 'best_quote', '')}")
                st.write(f"Sources: {', '.join(getattr(gap, 'sources', []))}")


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
    source_groups = set(filters.get("source_groups") or CATEGORIES)
    source = str(filters.get("source") or "")
    query = str(filters.get("query") or "").strip().lower()
    min_score = int(filters.get("min_score", 0))
    filtered: list[SignalRecord] = []
    for signal in signals:
        haystack = f"{signal.topic} {signal.title} {signal.summary} {signal.source} {signal.category}".lower()
        if source_groups and signal.category not in source_groups:
            continue
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


def _render_signal_explorer(
    signals: list[SignalRecord],
    filters: dict[str, Any] | None = None,
    key_prefix: str = "signals",
    page_payload: dict[str, object] | None = None,
) -> None:
    filtered = _apply_filters(signals, filters)
    cols = st.columns(4)
    cols[0].metric("Signals in view", len(filtered))
    cols[1].metric("Avg score", f"{sum(signal.score for signal in filtered) / max(len(filtered), 1):.1f}")
    cols[2].metric("Sources", len({signal.source for signal in filtered}))
    cols[3].metric("Topics", len({signal.topic for signal in filtered}))

    if not filtered:
        st.info("No signals match this view. Clear filters, enable the related source group, or refresh live data.")
        if page_payload:
            st.caption("Sources checked for this view")
            health_frame = _source_health_frame(page_payload)
            if not health_frame.empty:
                st.table(health_frame.head(12))
        return

    st.subheader("Visible Data")
    st.dataframe(_signal_preview_frame(filtered), width="stretch", hide_index=True, column_config=_signal_table_column_config())

    chart_cols = st.columns(2)
    category_frame = _category_distribution_frame(filtered)
    if not category_frame.empty:
        chart_cols[0].bar_chart(category_frame, x="category", y="signals")
    source_frame = _source_distribution_frame(filtered)
    if not source_frame.empty:
        chart_cols[1].bar_chart(source_frame, x="source", y="score")

    frame = _signal_display_frame(filtered)
    st.dataframe(frame, width="stretch", hide_index=True, column_config=_signal_table_column_config())
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
    signals = list(page_payload.get("signals", []))

    if page_key == "profile":
        profile = dict(page_payload.get("profile", {}))
        columns = st.columns(3)
        columns[0].metric("Skills", len(profile.get("skills", [])))
        columns[1].metric("Interests", len(profile.get("interests", [])))
        columns[2].metric("Alert threshold", int(profile.get("alert_threshold", 0)))
        st.subheader("Alert Readiness")
        st.dataframe(_alert_readiness_frame(), width="stretch", hide_index=True)
        st.json(profile)
        personalized = list(page_payload.get("personalized_signals", []))
        if personalized:
            st.subheader("Personalized Feed")
            _render_signal_explorer(personalized, filters, key_prefix="profile-personalized", page_payload=page_payload)
        return

    if page_key == "radar_search":
        st.text_input("Search collected signals", value=str((filters or {}).get("query") or "browser agents"), key="radar-search-query")
        st.json(page_payload.get("query_analysis", {}))

    if page_key == "briefing":
        analysis_artifacts = page_payload.get("analysis_artifacts", {})
        if isinstance(analysis_artifacts, dict) and analysis_artifacts:
            st.caption(f"Pipeline analysis: {analysis_artifacts.get('analysis_route', page_payload.get('llm_status', 'unknown'))}")
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

    if page_key == "github_radar":
        projects = _project_signals(signals)
        st.subheader("Projects")
        if projects:
            project_frame = _projects_to_frame(projects)
            st.dataframe(project_frame.head(12), width="stretch", hide_index=True, column_config=_signal_table_column_config())
            st.dataframe(project_frame, width="stretch", hide_index=True, column_config=_signal_table_column_config())
            _render_project_details(projects)
        else:
            st.info("No project repository signals match the current filters. Clear the sidebar filters or enable live collection.")

    if page_key == "skill_radar":
        recommendations = list(page_payload.get("skill_recommendations", []))
        if recommendations:
            st.subheader("Learning Path")
            st.dataframe(_skill_recommendations_to_frame(recommendations), width="stretch", hide_index=True)

    if page_key == "trend_velocity":
        historical = list(page_payload.get("historical_trends", []))
        if historical:
            st.subheader("Historical Velocity")
            st.dataframe(_objects_to_frame(historical), width="stretch", hide_index=True)
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
        if page_key == "startup_gaps":
            _render_startup_idea_cards(page_payload)
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

    _render_signal_explorer(signals, filters, key_prefix=page_key, page_payload=page_payload)


def render_dashboard(payload: dict[str, dict[str, object]], filters: dict[str, Any] | None = None) -> None:
    top = payload["briefing"]
    collection = dict(top.get("collection", {}))
    cols = st.columns(4)
    cols[0].metric("Active sources", int(top["active_sources"]))
    cols[1].metric("Signals", int(top["signals_24h"]))
    cols[2].metric("Registered sources", len(SOURCE_REGISTRY))
    cols[3].metric("Enabled by default", len(enabled_sources()))

    st.write(f"LLM route: `{top['llm_status']}`")
    freshness_cols = st.columns(4)
    freshness_cols[0].metric("Mode", str(collection.get("mode", "unknown")))
    freshness_cols[1].metric("Payload", "cache" if collection.get("loaded_from_cache") else "fresh")
    freshness_cols[2].metric("Collection seconds", f"{float(collection.get('duration_seconds') or 0):.1f}")
    freshness_cols[3].metric("Generated", _format_generated_at(collection.get("generated_at")))
    free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
    with st.expander("Free-only Guardrails", expanded=free_only):
        st.table(_free_only_guardrails_frame(free_only))
    st.download_button(
        "Download Daily Report",
        _build_markdown_report(payload).encode("utf-8"),
        file_name="internet-radar-daily-report.md",
        mime="text/markdown",
        key="download-daily-report",
    )
    st.subheader("Top Signals Preview")
    st.dataframe(
        _signal_preview_frame(list(top.get("signals", []))),
        width="stretch",
        hide_index=True,
        column_config=_signal_table_column_config(),
    )
    health_frame = _source_health_frame(top)
    if not health_frame.empty:
        with st.expander("Source Health", expanded=True):
            st.dataframe(health_frame, width="stretch", hide_index=True)
    tabs = st.tabs([page.title for page in PAGE_DEFINITIONS])
    for tab, page in zip(tabs, PAGE_DEFINITIONS, strict=True):
        with tab:
            render_page(page.key, payload[page.key], filters=filters)


def _format_generated_at(value: object) -> str:
    if not value:
        return "unknown"
    if isinstance(value, datetime):
        current = value
    else:
        try:
            current = datetime.fromisoformat(str(value))
        except ValueError:
            return str(value)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone().strftime("%H:%M:%S")


def render_page_entry(page_key: str) -> None:
    page = next((definition for definition in PAGE_DEFINITIONS if definition.key == page_key), PAGE_DEFINITIONS[0])
    st.set_page_config(page_title=f"Internet Radar v2 - {page.title}", layout="wide")
    st.title(page.title)
    payload = load_payload(use_live_network=os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1")
    render_page(page.key, payload[page.key])


@st.cache_data(ttl=300, show_spinner="Collecting live signals...")
def load_payload(use_live_network: bool = False, refresh_token: int = 0) -> dict[str, dict[str, object]]:
    if use_live_network and refresh_token == 0:
        cached = load_briefing_payload()
        if cached is not None:
            return _payload_from_briefing(cached)

    briefing = _collect_and_cache(use_live_network)
    return _payload_from_briefing(briefing)


def _collect_and_cache(use_live_network: bool) -> BriefingPayload:
    briefing = run_radar_once(use_live_network=use_live_network)
    if use_live_network:
        save_briefing_payload(briefing)
    return briefing


def _payload_from_briefing(briefing: BriefingPayload) -> dict[str, dict[str, object]]:
    profile = load_user_profile()
    return build_dashboard_payload(
        briefing.top_signals,
        active_sources=briefing.active_sources,
        llm_status=briefing.llm_status,
        profile=profile,
        generated_at=briefing.generated_at,
        collection_duration_seconds=briefing.collection_duration_seconds,
        collection_mode=briefing.collection_mode,
        loaded_from_cache=briefing.loaded_from_cache,
        source_health=briefing.source_health,
        source_counts=briefing.source_counts,
        source_durations_seconds=briefing.source_durations_seconds,
        historical_trends=briefing.historical_trends,
        analysis_artifacts=briefing.analysis_artifacts,
    )


def _maybe_start_background_refresh(use_live_network: bool) -> None:
    global _BACKGROUND_REFRESH_RUNNING
    if not use_live_network:
        return
    interval = int(os.getenv("INTERNET_RADAR_BACKGROUND_REFRESH_SECONDS", "3600"))
    if interval <= 0:
        return
    age = payload_cache_age_seconds()
    if age is not None and age < interval:
        return
    if _BACKGROUND_REFRESH_RUNNING:
        return
    _BACKGROUND_REFRESH_RUNNING = True

    def refresh() -> None:
        global _BACKGROUND_REFRESH_RUNNING
        try:
            _collect_and_cache(use_live_network=True)
        finally:
            _BACKGROUND_REFRESH_RUNNING = False

    Thread(target=refresh, name="internet-radar-refresh", daemon=True).start()


def main() -> None:
    st.set_page_config(page_title="Internet Radar v2", layout="wide")
    st.title("Internet Radar v2")
    st.caption("Local-first signal intelligence across code, social, news, jobs, research, finance, search, and app stores.")

    with st.sidebar:
        st.header("Collection")
        default_live = os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1"
        use_live = st.toggle("Use live network collectors", value=default_live)
        free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
        st.caption(f"Mode: {'free-only' if free_only else 'all configured'}")
        st.caption("Off uses deterministic sample signals. On calls no-key public APIs and falls back on errors.")
        if st.button("Refresh data"):
            st.session_state["refresh_token"] = int(st.session_state.get("refresh_token", 0)) + 1
            load_payload.clear()
        st.header("Source Groups")
        source_groups = st.multiselect("Visible groups", CATEGORIES, default=CATEGORIES)
        st.header("Filters")
        categories = st.multiselect(
            "Categories",
            CATEGORIES,
            default=[],
        )
        min_score = st.slider("Minimum score", min_value=0, max_value=100, value=0, step=5)
        query = st.text_input("Search text", value="")
        source_options = sorted({source.name for source in SOURCE_REGISTRY})
        source = st.selectbox("Source", [""] + source_options, index=0)

    refresh_token = int(st.session_state.get("refresh_token", 0))
    payload = load_payload(use_live_network=use_live, refresh_token=refresh_token)
    _maybe_start_background_refresh(use_live)
    render_dashboard(
        payload,
        filters={
            "categories": categories,
            "source_groups": source_groups,
            "min_score": min_score,
            "query": query,
            "source": source,
        },
    )


if __name__ == "__main__":
    main()
