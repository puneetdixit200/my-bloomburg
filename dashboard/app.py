from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from html import escape
import os
from pathlib import Path
import re
from threading import Thread
from typing import Any

import pandas as pd
import streamlit as st

from dashboard.theme import (
    COLORS,
    alert_card_html,
    inject_custom_css,
    insight_card_html,
    project_detail_html,
    radar_bar_chart,
    render_briefing_hero,
    render_glow_metric,
    render_idea_card,
    section_header_html,
    signal_card_html,
    source_status_html,
    velocity_sparkline,
)
from internet_radar.alerts.dispatcher import alert_readiness
from internet_radar.alerts.outbox import AlertOutbox
from internet_radar.config.settings import load_user_profile
from internet_radar.dashboard_data import PAGE_DEFINITIONS, build_dashboard_payload
from internet_radar.operations.readiness import build_make_real_readiness, readiness_frame
from internet_radar.pipeline import run_radar_once
from internet_radar.sources.registry import SOURCE_REGISTRY
from internet_radar.storage.analytics import compute_signal_analytics
from internet_radar.storage.models import BriefingPayload, SignalRecord
from internet_radar.storage.payload_cache import load_briefing_payload, payload_cache_age_seconds, save_briefing_payload


CATEGORIES = ["code", "social", "news", "jobs", "hackathons", "research", "finance", "search", "app_stores"]
_BACKGROUND_REFRESH_RUNNING = False
_APP_FILE = Path(__file__).resolve()
_PAGES_DIR = _APP_FILE.parent / "pages"
SIDEBAR_NAV_ITEMS = [
    (_PAGES_DIR / "00_briefing.py", "BRIEFING"),
    (_PAGES_DIR / "01_github_radar.py", "GITHUB RADAR"),
    (_PAGES_DIR / "02_hackathon_radar.py", "HACKATHON RADAR"),
    (_PAGES_DIR / "03_internship_radar.py", "INTERNSHIP RADAR"),
    (_PAGES_DIR / "04_startup_gaps.py", "STARTUP GAPS"),
    (_PAGES_DIR / "05_trend_velocity.py", "TREND VELOCITY"),
    (_PAGES_DIR / "06_research_radar.py", "RESEARCH RADAR"),
    (_PAGES_DIR / "07_funding_radar.py", "FUNDING RADAR"),
    (_PAGES_DIR / "08_skill_radar.py", "SKILL RADAR"),
    (_PAGES_DIR / "09_community_radar.py", "COMMUNITY RADAR"),
    (_PAGES_DIR / "10_app_store_radar.py", "APP STORE RADAR"),
    (_PAGES_DIR / "11_search_radar.py", "SEARCH RADAR"),
    (_PAGES_DIR / "12_profile.py", "PROFILE"),
    (_APP_FILE, "APP REPORT"),
]


def _render_sidebar_navigation() -> None:
    for page_path, label in SIDEBAR_NAV_ITEMS:
        st.page_link(page_path, label=label, use_container_width=True)
    st.markdown('<hr style="border:none;border-top:1px solid #30363D;margin:1.2rem 0;">', unsafe_allow_html=True)


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
                "summary": signal.summary,
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


def _alert_outbox_frame(db_path: str | Path | None = None) -> pd.DataFrame:
    path = db_path or os.getenv("INTERNET_RADAR_ALERT_OUTBOX_DB") or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite")
    rows = []
    for item in AlertOutbox(path).list_recent(limit=25):
        rows.append(
            {
                "status": item.status,
                "channel": item.channel,
                "signal_id": item.signal_id,
                "kind": item.kind,
                "attempts": item.attempts,
                "last_error": item.last_error,
                "updated_at": item.updated_at,
            }
        )
    return pd.DataFrame(rows)


def _make_real_readiness_frame(page_payload: dict[str, object], db_path: str | Path | None = None) -> pd.DataFrame:
    collection = dict(page_payload.get("collection", {}))
    collection_mode = str(collection.get("mode") or "sample")
    if collection_mode not in {"live", "sample"}:
        collection_mode = "sample"
    payload = BriefingPayload(
        active_sources=int(page_payload.get("active_sources", 0) or 0),
        signals_24h=int(page_payload.get("signals_24h", 0) or 0),
        top_signals=list(page_payload.get("signals", [])),
        source_health=dict(page_payload.get("source_health", {})),
        source_counts=dict(page_payload.get("source_counts", {})),
        source_durations_seconds=dict(page_payload.get("source_durations_seconds", {})),
        historical_trends=list(page_payload.get("historical_trends", [])),
        analysis_artifacts=dict(page_payload.get("analysis_artifacts", {})),
        llm_status=str(page_payload.get("llm_status", "unknown")),
        collection_duration_seconds=float(collection.get("duration_seconds") or 0.0),
        collection_mode=collection_mode,
        loaded_from_cache=bool(collection.get("loaded_from_cache", False)),
    )
    return readiness_frame(build_make_real_readiness(db_path=db_path, payload=payload))


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
    columns = ["topic", "title", "source", "category", "summary", "url"]
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
    return {}


def _drop_score_columns(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    drop_columns = [
        column
        for column in frame.columns
        if "score" in str(column).lower() or str(column).lower() == "relevance"
    ]
    return frame.drop(columns=drop_columns, errors="ignore")


def _link_columns(frame: pd.DataFrame) -> list[str]:
    link_names = {"url", "link", "href", "source_url", "source_link", "permalink"}
    return [column for column in frame.columns if str(column).lower() in link_names]


def _link_label_column(frame: pd.DataFrame) -> str | None:
    for column in ("topic", "title", "project", "skill", "problem", "name", "signal_id"):
        if column in frame.columns:
            return column
    return None


def _prepare_visible_frame(frame: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    visible = _drop_score_columns(frame).copy()
    link_columns = _link_columns(visible)
    if not link_columns:
        return visible, False
    label_column = _link_label_column(visible)
    if not label_column:
        return visible.drop(columns=link_columns, errors="ignore"), False
    link_column = link_columns[0]
    has_links = False
    for index, row in visible.iterrows():
        url = str(row.get(link_column) or "").strip()
        label = str(row.get(label_column) or url).strip()
        if url and label:
            visible.at[index, label_column] = (
                f'<a href="{escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'
            )
            has_links = True
    return visible.drop(columns=link_columns, errors="ignore"), has_links


def _export_visible_frame(frame: pd.DataFrame) -> pd.DataFrame:
    visible = _drop_score_columns(frame)
    return visible.drop(columns=_link_columns(visible), errors="ignore")


def _render_table(frame: pd.DataFrame, *, height: int | None = None) -> None:
    visible, has_links = _prepare_visible_frame(frame)
    if visible.empty or not has_links:
        kwargs: dict[str, object] = {"width": "stretch", "hide_index": True}
        if height is not None:
            kwargs["height"] = height
        st.dataframe(visible, **kwargs)
        return
    st.markdown(_frame_to_html(visible), unsafe_allow_html=True)


def _frame_to_html(frame: pd.DataFrame) -> str:
    headers = "".join(f"<th>{escape(str(column).replace('_', ' ').title())}</th>" for column in frame.columns)
    rows = []
    for _, row in frame.iterrows():
        cells = "".join(f"<td>{_table_cell_html(row[column])}</td>" for column in frame.columns)
        rows.append(f"<tr>{cells}</tr>")
    return f'<div class="radar-table-wrap"><table class="radar-table"><thead><tr>{headers}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def _table_cell_html(value: object) -> str:
    text = "" if value is None else str(value)
    if text.startswith("<a ") and "</a>" in text:
        return text
    return escape(text)


def _public_text(value: object) -> str:
    text = str(value or "")
    text = re.sub(r"(?im)^\s*(?:top\s+score|avg\s+score|average\s+score|score)\s*:?\s*\d+(?:\.\d+)?(?:/\d+)?\s*$", "", text)
    text = re.sub(r"\b(?:top\s+score|avg\s+score|average\s+score|score)\s*:?\s*\d+(?:\.\d+)?(?:/\d+)?\b", "", text, flags=re.I)
    text = re.sub(r"\b(?:with|at)\s+(?:a\s+)?score\s+(?:of\s+)?\d+(?:\.\d+)?(?:/\d+)?\b", "", text, flags=re.I)
    text = re.sub(r"\bscored\s+\d+(?:\.\d+)?(?:/\d+)?\b", "", text, flags=re.I)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -|\n\t")


def _public_json(value: object) -> object:
    if isinstance(value, dict):
        return {key: _public_json(item) for key, item in value.items() if "score" not in str(key).lower()}
    if isinstance(value, list):
        return [_public_json(item) for item in value]
    if isinstance(value, str):
        return _public_text(value)
    return value


def _render_section_header(title: str, detail: str = "") -> None:
    st.markdown(section_header_html(title, detail), unsafe_allow_html=True)


def _signal_action(signal: SignalRecord) -> str:
    if signal.score >= 90:
        return "ACT NOW"
    if signal.score >= 75:
        return "STRONG"
    return "WATCH"


def _render_signal_cards(signals: list[SignalRecord], limit: int = 4) -> None:
    for signal in signals[:limit]:
        st.markdown(
            signal_card_html(
                signal.title,
                signal.source,
                signal.category,
                signal.score,
                summary=_public_text(signal.summary or signal.topic),
                url=signal.url,
                action=_signal_action(signal),
            ),
            unsafe_allow_html=True,
        )


def _format_count(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value or "")
    if numeric >= 1_000_000:
        return f"{numeric / 1_000_000:.1f}M"
    if numeric >= 1_000:
        return f"{numeric / 1_000:.1f}K"
    return str(int(numeric))


def _sparkline_values(signal: SignalRecord) -> list[int]:
    base = max(10, min(int(signal.score), 100))
    previous = max(5, base - max(8, int(signal.velocity or 12)))
    midpoint = int((base + previous) / 2)
    return [max(0, previous - 8), previous, midpoint, min(100, midpoint + 7), base]


def _freshness_bucket_counts(signals: list[SignalRecord]) -> dict[str, int]:
    now = datetime.now(UTC)
    buckets = {"< 6h": 0, "< 24h": 0, "< 72h": 0}
    for signal in signals:
        observed = signal.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=UTC)
        hours = (now - observed).total_seconds() / 3600
        if hours <= 6:
            buckets["< 6h"] += 1
        if hours <= 24:
            buckets["< 24h"] += 1
        if hours <= 72:
            buckets["< 72h"] += 1
    return buckets


def _page_metric_values(signals: list[SignalRecord]) -> dict[str, int | str]:
    return {
        "signals": len(signals),
        "sources": len({signal.source for signal in signals}),
        "topics": len({signal.topic for signal in signals}),
        "categories": len({signal.category for signal in signals}),
    }


def _render_page_metric_strip(signals: list[SignalRecord]) -> None:
    metrics = _page_metric_values(signals)
    columns = st.columns(4)
    with columns[0]:
        render_glow_metric(st, "Signals", metrics["signals"], "teal")
    with columns[1]:
        render_glow_metric(st, "Sources", metrics["sources"], "sky")
    with columns[2]:
        render_glow_metric(st, "Topics", metrics["topics"], "purple")
    with columns[3]:
        render_glow_metric(st, "Categories", metrics["categories"], "emerald")


def _project_signals(signals: list[SignalRecord]) -> list[SignalRecord]:
    project_sources = {"GitHub Search", "GitHub Trending", "GitLab Explore", "MCP Servers Directory"}
    return [signal for signal in signals if signal.source in project_sources and _is_project_url(signal.url)]


def _projects_to_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
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
        if isinstance(item, dict):
            rows.append(item)
        elif is_dataclass(item):
            rows.append(asdict(item))
        elif hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        else:
            rows.append(getattr(item, "__dict__", {}))
    return pd.DataFrame(rows)


def _value(item: object, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _list_value(item: object, key: str) -> list[object]:
    value = _value(item, key, [])
    return value if isinstance(value, list) else []


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
            title_text = signal.topic or signal.title
            linked_title = f"[{title_text}]({signal.url})" if signal.url else title_text
            lines.append(f"- {linked_title}: {signal.title} ({signal.source})")
        lines.append("")
    return "\n".join(lines)


def _render_project_details(projects: list[SignalRecord]) -> None:
    if not projects:
        return
    labels = [_project_name(signal) for signal in projects]
    selected = st.selectbox("Inspect project", labels, key="inspect-project")
    signal = projects[labels.index(selected)]
    st.markdown(
        project_detail_html(
            _project_name(signal),
            signal.score,
            _format_count(signal.metadata.get("stars", "")),
            str(signal.metadata.get("language", "") or "unknown"),
            signal.source,
            _public_text(signal.summary or signal.title),
            _project_action(signal),
            url=signal.url,
        ),
        unsafe_allow_html=True,
    )


def _render_startup_idea_cards(page_payload: dict[str, object]) -> None:
    analyses = list(page_payload.get("gap_analyses", []))
    gaps = list(page_payload.get("gap_clusters", []))
    if not analyses and not gaps:
        return
    _render_section_header("Top Gaps", "pain signals and product gaps")
    for index, analysis in enumerate(analyses[:5], start=1):
        ideas = _list_value(analysis, "startup_ideas")
        patterns = _list_value(analysis, "patterns")
        idea = ideas[0] if ideas else None
        pattern = patterns[0] if patterns else None
        title = _value(idea, "idea", None) or _value(analysis, "topic", f"Idea {index}")
        render_idea_card(
            st,
            title=str(title),
            problem=str(_value(pattern, "problem", _value(analysis, "topic", "")) if pattern else _value(analysis, "topic", "")),
            quote=str(_value(pattern, "representative_quote", "") if pattern else ""),
            pain_level=int(_value(pattern, "pain_level", 5) if pattern else 5),
            complaints=int(_value(pattern, "complaints", 0) if pattern else 0),
            score=int(_value(idea, "score", 0) if idea else _value(analysis, "confidence", 0)),
            sources=[str(source) for source in (_value(pattern, "sources", []) if pattern else [])],
            next_step=str(_value(analysis, "recommended_action", "Validate the pain with five target users.")),
            market=str(_value(idea, "market_size", "") if idea else ""),
            competition=str(_value(idea, "competition_level", "") if idea else ""),
            index=index,
        )
    if not analyses:
        for index, gap in enumerate(gaps[:5], start=1):
            render_idea_card(
                st,
                title=str(getattr(gap, "startup_idea", "Startup idea")),
                problem=str(getattr(gap, "problem", "")),
                quote=str(getattr(gap, "best_quote", "")),
                pain_level=int(getattr(gap, "pain_level", 5)),
                complaints=int(getattr(gap, "complaint_count", 0)),
                score=int(getattr(gap, "score", 0)),
                sources=[str(source) for source in getattr(gap, "sources", [])],
                next_step="Run a focused landing-page or outreach validation test.",
                index=index,
            )


def _category_distribution_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return pd.DataFrame(compute_signal_analytics(signals).category_distribution)


def _source_distribution_frame(signals: list[SignalRecord]) -> pd.DataFrame:
    return pd.DataFrame(compute_signal_analytics(signals).source_distribution)


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
    with cols[0]:
        render_glow_metric(st, "Signals in View", len(filtered), "teal")
    with cols[1]:
        render_glow_metric(st, "Sources", len({signal.source for signal in filtered}), "sky")
    with cols[2]:
        render_glow_metric(st, "Topics", len({signal.topic for signal in filtered}), "purple")
    with cols[3]:
        render_glow_metric(st, "Categories", len({signal.category for signal in filtered}), "emerald")

    if not filtered:
        st.info("No signals match this view. Clear filters, enable the related source group, or refresh live data.")
        if page_payload:
            st.caption("Sources checked for this view")
            health_frame = _source_health_frame(page_payload)
            if not health_frame.empty:
                _render_table(health_frame.head(12))
        return

    _render_section_header("Top Signals", "ranked by relevance")
    _render_signal_cards(filtered, limit=4)
    _render_table(_signal_preview_frame(filtered))

    _render_section_header("Charts", "distribution and coverage")
    chart_cols = st.columns(2)
    category_frame = _category_distribution_frame(filtered)
    if not category_frame.empty:
        chart_cols[0].plotly_chart(
            radar_bar_chart(category_frame, "category", "signals", COLORS["teal"], title="Signal Distribution"),
            width="stretch",
            key=f"{key_prefix}-category-distribution",
        )
    source_frame = _source_distribution_frame(filtered)
    if not source_frame.empty:
        chart_cols[1].plotly_chart(
            radar_bar_chart(source_frame.head(12), "source", "signals", COLORS["purple"], title="Source Coverage"),
            width="stretch",
            key=f"{key_prefix}-source-strength",
        )

    _render_section_header("Visible Data", "exportable table")
    frame = _signal_display_frame(filtered)
    _render_table(frame)
    st.download_button(
        "Download CSV",
        _export_visible_frame(frame).to_csv(index=False).encode("utf-8"),
        file_name="internet-radar-signals.csv",
        mime="text/csv",
        key=f"download-{key_prefix}",
    )
    selected = st.selectbox("Inspect signal", [signal.title for signal in filtered], key=f"inspect-{key_prefix}")
    signal = next(item for item in filtered if item.title == selected)
    with st.expander("Signal detail", expanded=False):
        st.json(_public_signal_json(signal))


def _public_signal_json(signal: SignalRecord) -> dict[str, object]:
    data = signal.model_dump(mode="json")
    data.pop("score", None)
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        data["metadata"] = {key: value for key, value in metadata.items() if "score" not in str(key).lower()}
    return dict(_public_json(data))


def render_page(page_key: str, page_payload: dict[str, object], filters: dict[str, Any] | None = None) -> None:
    _render_section_header(str(page_payload["title"]).upper(), str(page_payload["description"]))
    signals = list(page_payload.get("signals", []))
    if page_key != "profile":
        _render_page_metric_strip(signals)

    if page_key == "profile":
        profile = dict(page_payload.get("profile", {}))
        columns = st.columns(3)
        with columns[0]:
            render_glow_metric(st, "Skills", len(profile.get("skills", [])), "teal")
        with columns[1]:
            render_glow_metric(st, "Interests", len(profile.get("interests", [])), "purple")
        with columns[2]:
            render_glow_metric(st, "Alert Channels", len(profile.get("notification_channels", [])), "amber")
        _render_section_header("Alert Readiness")
        _render_table(_alert_readiness_frame())
        outbox_frame = _alert_outbox_frame()
        if not outbox_frame.empty:
            _render_section_header("Alert Outbox", "latest delivery attempts")
            _render_table(outbox_frame)
        with st.expander("Profile JSON", expanded=False):
            st.json(profile)
        personalized = list(page_payload.get("personalized_signals", []))
        if personalized:
            _render_section_header("Personalized Feed")
            _render_signal_explorer(personalized, filters, key_prefix="profile-personalized", page_payload=page_payload)
        return

    if page_key == "radar_search":
        st.text_input("Search collected signals", value=str((filters or {}).get("query") or "browser agents"), key="radar-search-query")
        with st.expander("Query Analysis", expanded=True):
            st.json(_public_json(page_payload.get("query_analysis", {})))

    if page_key == "briefing":
        analysis_artifacts = page_payload.get("analysis_artifacts", {})
        if isinstance(analysis_artifacts, dict) and analysis_artifacts:
            st.caption(f"Pipeline analysis: {analysis_artifacts.get('analysis_route', page_payload.get('llm_status', 'unknown'))}")
        signal_summary = page_payload.get("signal_summary")
        daily_briefing = page_payload.get("daily_briefing", {})
        headline = str(_value(signal_summary, "headline", "") if signal_summary else "")
        if not headline and isinstance(daily_briefing, dict):
            headline = str(daily_briefing.get("headline") or "")
        if not headline:
            headline = "High-signal opportunities across your sources"
        narrative = ""
        if isinstance(daily_briefing, dict):
            narrative = str(daily_briefing.get("narrative") or "")
        if not narrative and signal_summary:
            narrative = str(_value(signal_summary, "next_action", ""))
        render_briefing_hero(st, _public_text(headline), _public_text(narrative), len(list(page_payload.get("alerts", []))))
        llm_insight = page_payload.get("llm_generated_insight", {})
        if isinstance(llm_insight, dict) and llm_insight:
            _render_section_header("LLM Insight")
            public_insight = _public_json(llm_insight)
            st.markdown(insight_card_html(public_insight if isinstance(public_insight, dict) else {}), unsafe_allow_html=True)
        alerts = list(page_payload.get("alerts", []))
        if alerts:
            _render_section_header("Act Now", f"{len(alerts)} alert candidates")
            alert_columns = st.columns(2)
            for index, alert in enumerate(alerts[:6]):
                with alert_columns[index % 2]:
                    st.markdown(
                        alert_card_html(alert.title, alert.kind, alert.score, _public_text(alert.body), alert.channels),
                        unsafe_allow_html=True,
                    )

    if page_key == "github_radar":
        projects = _project_signals(signals)
        if projects:
            _render_section_header("Velocity Spotlight", "repository and package momentum")
            spotlight = projects[:3]
            spotlight_cols = st.columns(len(spotlight))
            dates = ["4d", "3d", "2d", "1d", "now"]
            for index, (column, signal) in enumerate(zip(spotlight_cols, spotlight, strict=False)):
                with column:
                    render_glow_metric(
                        st,
                        _project_name(signal),
                        _format_count(signal.metadata.get("stars", signal.score)),
                        "teal" if signal.source == "GitHub Trending" else "sky",
                    )
                    st.plotly_chart(
                        velocity_sparkline(dates, _sparkline_values(signal), COLORS["teal"], title="velocity"),
                        width="stretch",
                        key=f"github-velocity-{index}",
                    )
            _render_section_header("Trending Projects")
            project_frame = _projects_to_frame(projects)
            _render_table(project_frame.head(12))
            _render_signal_cards(projects, limit=3)
            _render_section_header("Project Detail")
            _render_project_details(projects)
        else:
            st.info("No project repository signals match the current filters. Clear the sidebar filters or enable live collection.")

    if page_key == "skill_radar":
        recommendations = list(page_payload.get("skill_recommendations", []))
        if recommendations:
            _render_section_header("Learning Path", "skills heating up across jobs and code")
            _render_table(_skill_recommendations_to_frame(recommendations))

    if page_key == "trend_velocity":
        historical = list(page_payload.get("historical_trends", []))
        agreements = list(page_payload.get("source_agreements", []))
        if agreements:
            _render_section_header("Source Agreement", "cross-source confidence")
            _render_table(_source_agreements_to_frame(agreements))
            for agreement in agreements[:4]:
                st.markdown(
                    signal_card_html(
                        str(getattr(agreement, "topic", "Trend")),
                        ", ".join(getattr(agreement, "sources", [])[:3]),
                        "trend",
                        int(getattr(agreement, "score", 0)),
                        summary=f"{getattr(agreement, 'source_count', 0)}/{getattr(agreement, 'known_source_count', 0)} sources confirming.",
                        action=str(getattr(agreement, "verdict", "WATCH")),
                    ),
                    unsafe_allow_html=True,
                )
        if historical:
            _render_section_header("Historical Velocity")
            _render_table(_objects_to_frame(historical))
        correlations = list(page_payload.get("trend_correlations", []))
        if correlations:
            _render_section_header("Trend Correlations")
            _render_table(_objects_to_frame(correlations))
        predictions = list(page_payload.get("trend_predictions", []))
        if predictions:
            _render_section_header("Trend Predictions")
            _render_table(_objects_to_frame(predictions))

    if page_key == "hackathon_radar":
        if signals:
            _render_section_header("Apply Now", "fresh opportunities")
            card_cols = st.columns(2)
            for index, signal in enumerate(signals[:4]):
                prize = signal.metadata.get("prize_pool") or signal.metadata.get("prize") or ""
                days_left = signal.metadata.get("days_left") or signal.metadata.get("deadline_days") or ""
                summary_bits = [signal.summary or signal.topic]
                if prize:
                    summary_bits.append(f"Prize: {prize}")
                if days_left != "":
                    summary_bits.append(f"Deadline: {days_left} days")
                with card_cols[index % 2]:
                    st.markdown(
                        signal_card_html(
                            signal.title,
                            signal.source,
                            signal.category,
                            signal.score,
                            summary=_public_text(" | ".join(str(bit) for bit in summary_bits if bit)),
                            url=signal.url,
                            action="APPLY NOW" if signal.score >= 80 else "WATCH",
                        ),
                        unsafe_allow_html=True,
                    )
        predictions = list(page_payload.get("crowd_predictions", []))
        if predictions:
            _render_section_header("Crowd Prediction")
            _render_table(_objects_to_frame(predictions))

    if page_key == "internship_radar" and signals:
        _render_section_header("Freshness Priority")
        buckets = _freshness_bucket_counts(signals)
        bucket_cols = st.columns(3)
        for column, (label, count) in zip(bucket_cols, buckets.items(), strict=True):
            with column:
                render_glow_metric(st, label, count, "sky")
        _render_section_header("Apply Today", "fresh jobs and skill match")
        _render_signal_cards(signals, limit=5)

    if page_key == "research_radar":
        academic_signals = list(page_payload.get("academic_signals", []))
        if signals:
            _render_section_header("Academic Momentum")
            _render_signal_cards(signals, limit=4)
        if academic_signals:
            _render_section_header("Research Detail")
            _render_table(_objects_to_frame(academic_signals))

    if page_key == "funding_radar":
        funding_signals = list(page_payload.get("funding_signals", []))
        if signals:
            _render_section_header("Market Validation")
            _render_signal_cards(signals, limit=4)
        if funding_signals:
            _render_section_header("Funding Detail")
            _render_table(_objects_to_frame(funding_signals))

    if page_key in {"startup_gaps", "app_store_pain"}:
        if page_key == "startup_gaps":
            _render_startup_idea_cards(page_payload)
        analyses = list(page_payload.get("gap_analyses", []))
        if page_key == "startup_gaps" and analyses:
            _render_section_header("Gap Analysis")
            _render_table(_objects_to_frame(analyses))
        validations = list(page_payload.get("idea_validations", []))
        if page_key == "startup_gaps" and validations:
            _render_section_header("Idea Validation")
            _render_table(_objects_to_frame(validations))
        gap_key = "pain_clusters" if page_key == "app_store_pain" else "gap_clusters"
        gaps = list(page_payload.get(gap_key, []))
        if gaps:
            _render_section_header("Pain Clusters")
            _render_table(_gaps_to_frame(gaps))
        semantic_clusters = list(page_payload.get("semantic_clusters", []))
        if semantic_clusters:
            _render_section_header("Semantic Clusters")
            _render_table(_semantic_clusters_to_frame(semantic_clusters))

    if page_key == "community_pulse":
        summary = page_payload.get("sentiment_summary", {})
        if isinstance(summary, dict) and any(int(value) for value in summary.values()):
            _render_section_header("Sentiment Summary")
            _render_table(_sentiment_to_frame(summary))

    _render_signal_explorer(signals, filters, key_prefix=page_key, page_payload=page_payload)


def render_dashboard(payload: dict[str, dict[str, object]], filters: dict[str, Any] | None = None) -> None:
    top = payload["briefing"]
    collection = dict(top.get("collection", {}))
    alerts = list(top.get("alerts", []))
    top_signals = list(top.get("signals", []))
    cols = st.columns(4)
    with cols[0]:
        render_glow_metric(st, "Active Sources", int(top["active_sources"]), "teal")
    with cols[1]:
        render_glow_metric(st, "Signals", int(top["signals_24h"]), "purple")
    with cols[2]:
        render_glow_metric(st, "Act Now", len(alerts), "amber")
    with cols[3]:
        render_glow_metric(st, "Categories", len({signal.category for signal in top_signals}), "emerald")

    st.caption(f"LLM route: `{top['llm_status']}`")
    freshness_cols = st.columns(4)
    with freshness_cols[0]:
        render_glow_metric(st, "Mode", str(collection.get("mode", "unknown")), "sky")
    with freshness_cols[1]:
        render_glow_metric(st, "Payload", "cache" if collection.get("loaded_from_cache") else "fresh", "emerald")
    with freshness_cols[2]:
        render_glow_metric(st, "Collection Sec", f"{float(collection.get('duration_seconds') or 0):.1f}", "orange")
    with freshness_cols[3]:
        render_glow_metric(st, "Generated", _format_generated_at(collection.get("generated_at")), "teal")
    readiness = _make_real_readiness_frame(top)
    with st.expander("Make It Real Readiness", expanded=bool((readiness["status"] == "blocked").any())):
        _render_table(readiness)
    st.download_button(
        "Download Daily Report",
        _build_markdown_report(payload).encode("utf-8"),
        file_name="internet-radar-daily-report.md",
        mime="text/markdown",
        key="download-daily-report",
    )
    _render_section_header("Top Signals Preview", "balanced across sources")
    _render_signal_cards(top_signals, limit=4)
    _render_table(_signal_preview_frame(top_signals))
    health_frame = _source_health_frame(top)
    if not health_frame.empty:
        with st.expander("Source Health", expanded=True):
            status_rows = "".join(
                f"<div style='margin:0.35rem 0;'>{source_status_html(row.status)} <span style='color:#8B949E;margin-left:0.5rem;'>{row.source}</span></div>"
                for row in health_frame.head(18).itertuples(index=False)
            )
            st.markdown(status_rows, unsafe_allow_html=True)
            _render_table(health_frame)
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
    inject_custom_css()
    st.title(page.title)
    with st.sidebar:
        _render_sidebar_navigation()
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
    inject_custom_css()
    st.title("Internet Radar v2")
    st.caption("Local-first signal intelligence across code, social, news, jobs, research, finance, search, and app stores.")

    with st.sidebar:
        _render_sidebar_navigation()
        st.markdown(
            """
            <div style="text-align:center;padding:1rem 0 1.5rem;">
                <div style="font-size:1.5rem;font-weight:900;letter-spacing:0;">
                    <span style="color:#14B8A6;">INTERNET</span>
                    <span style="color:#F3F6FA;"> RADAR</span>
                </div>
                <div style="font-size:0.65rem;color:#484F58;text-transform:uppercase;letter-spacing:0.2em;margin-top:4px;">
                    SIGNAL INTELLIGENCE PLATFORM
                </div>
            </div>
            <hr style="border:none;border-top:1px solid #21262D;margin:0;">
            """,
            unsafe_allow_html=True,
        )
        st.markdown('<div class="micro-label" style="margin:1.5rem 0 0.5rem;">COLLECTION</div>', unsafe_allow_html=True)
        default_live = os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1"
        use_live = st.toggle("LIVE NETWORK", value=default_live)
        free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
        st.caption("FREE-ONLY" if free_only else "ALL CONFIGURED")
        if st.button("REFRESH DATA", use_container_width=True):
            st.session_state["refresh_token"] = int(st.session_state.get("refresh_token", 0)) + 1
            load_payload.clear()
        st.markdown('<div class="micro-label" style="margin:1.5rem 0 0.5rem;">SOURCE GROUPS</div>', unsafe_allow_html=True)
        source_groups = st.multiselect(
            "VISIBLE GROUPS",
            CATEGORIES,
            default=CATEGORIES,
            format_func=lambda value: str(value).upper(),
        )
        st.markdown('<div class="micro-label" style="margin:1.5rem 0 0.5rem;">FILTERS</div>', unsafe_allow_html=True)
        categories = st.multiselect(
            "CATEGORIES",
            CATEGORIES,
            default=[],
            format_func=lambda value: str(value).upper(),
        )
        query = st.text_input("SEARCH", value="", placeholder="E.G. BROWSER AGENTS")
        source_options = sorted({source.name for source in SOURCE_REGISTRY})
        source = st.selectbox(
            "SOURCE",
            [""] + source_options,
            index=0,
            format_func=lambda value: "ALL" if value == "" else str(value).upper(),
        )

    refresh_token = int(st.session_state.get("refresh_token", 0))
    payload = load_payload(use_live_network=use_live, refresh_token=refresh_token)
    _maybe_start_background_refresh(use_live)
    render_dashboard(
        payload,
        filters={
            "categories": categories,
            "source_groups": source_groups,
            "min_score": 0,
            "query": query,
            "source": source,
        },
    )


if __name__ == "__main__":
    main()
