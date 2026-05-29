from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import re
from typing import Any

import pandas as pd
import plotly.graph_objects as go


COLORS = {
    "bg_primary": "#0A0D12",
    "bg_card": "#0E1117",
    "bg_elevated": "#161B22",
    "bg_hover": "#1C2128",
    "bg_glass": "rgba(14, 17, 23, 0.7)",
    "teal": "#14B8A6",
    "purple": "#8B5CF6",
    "amber": "#F59E0B",
    "emerald": "#10B981",
    "rose": "#F43F5E",
    "sky": "#38BDF8",
    "orange": "#FB923C",
    "text_primary": "#F3F6FA",
    "text_secondary": "#8B949E",
    "text_muted": "#484F58",
    "border_subtle": "#21262D",
    "border_accent": "#30363D",
}


CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --text-xs: 0.75rem;
    --text-sm: 0.875rem;
    --text-base: 1rem;
    --text-lg: 1.125rem;
    --text-xl: 1.5rem;
    --text-2xl: 2rem;
    --text-3xl: 2.5rem;
    --text-4xl: 3.5rem;
}

.stApp {
    font-family: var(--font-sans) !important;
    background: #0A0D12 !important;
    color: #F3F6FA !important;
}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 3rem !important;
}

.glass-card {
    background: rgba(14, 17, 23, 0.65);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 16px;
    padding: 1.25rem;
    transition: all 0.24s ease;
    overflow-wrap: anywhere;
}
.glass-card:hover {
    border-color: rgba(255, 255, 255, 0.12);
    transform: translateY(-1px);
    box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
}

.glow-card {
    background: rgba(14, 17, 23, 0.82);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 12px;
    padding: 1.1rem;
    position: relative;
    overflow: hidden;
    min-height: 114px;
}
.glow-card::before {
    content: '';
    position: absolute;
    inset: -80%;
    background: radial-gradient(circle, var(--glow-color, #14B8A6) 0%, transparent 58%);
    opacity: 0.07;
    pointer-events: none;
}
.glow-card:hover::before { opacity: 0.13; }
.glow-teal { --glow-color: #14B8A6; border-color: rgba(20, 184, 166, 0.3); }
.glow-purple { --glow-color: #8B5CF6; border-color: rgba(139, 92, 246, 0.3); }
.glow-amber { --glow-color: #F59E0B; border-color: rgba(245, 158, 11, 0.3); }
.glow-emerald { --glow-color: #10B981; border-color: rgba(16, 185, 129, 0.3); }
.glow-rose { --glow-color: #F43F5E; border-color: rgba(244, 63, 94, 0.3); }
.glow-sky { --glow-color: #38BDF8; border-color: rgba(56, 189, 248, 0.3); }
.glow-orange { --glow-color: #FB923C; border-color: rgba(251, 146, 60, 0.3); }

.metric-label,
.micro-label {
    font-size: 0.72rem;
    color: #8B949E;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 700;
}
.metric-value {
    font-size: 1.85rem;
    line-height: 1.1;
    font-weight: 850;
    font-family: var(--font-mono);
    color: #F3F6FA;
    margin-top: 0.35rem;
}
.metric-delta {
    font-size: 0.78rem;
    color: #10B981;
    margin-top: 0.35rem;
    font-weight: 650;
}

.pain-bar-track {
    height: 8px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 4px;
    overflow: hidden;
}
.pain-bar-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 0.6s ease;
}
.pain-low .pain-bar-fill { background: linear-gradient(90deg, #F59E0B, #FB923C); }
.pain-medium .pain-bar-fill { background: linear-gradient(90deg, #FB923C, #EF4444); }
.pain-high .pain-bar-fill { background: linear-gradient(90deg, #EF4444, #DC2626); }

.source-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 9999px;
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin: 0 4px 4px 0;
    background: rgba(255, 255, 255, 0.06);
    color: #8B949E;
    border: 1px solid rgba(255, 255, 255, 0.08);
}

.status-live,
.status-fallback,
.status-error {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-weight: 700;
}
.status-live { color: #10B981; }
.status-fallback { color: #F59E0B; }
.status-error { color: #EF4444; }
.status-live::before,
.status-fallback::before,
.status-error::before {
    content: '';
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: currentColor;
    box-shadow: 0 0 10px currentColor;
}

.verdict-act-now,
.verdict-strong,
.verdict-watch {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 6px;
    font-weight: 800;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    white-space: nowrap;
}
.verdict-act-now { background: rgba(239, 68, 68, 0.12); color: #EF4444; animation: pulse-glow 2s infinite; }
.verdict-strong { background: rgba(16, 185, 129, 0.12); color: #10B981; }
.verdict-watch { background: rgba(107, 114, 128, 0.12); color: #8B949E; }

@keyframes pulse-glow {
    0%, 100% { box-shadow: 0 0 8px rgba(239, 68, 68, 0.24); }
    50% { box-shadow: 0 0 20px rgba(239, 68, 68, 0.42); }
}

.section-header {
    font-size: 1.125rem;
    font-weight: 800;
    color: #F3F6FA;
    margin: 2rem 0 1rem 0;
    padding-bottom: 0.55rem;
    border-bottom: 1px solid #21262D;
    letter-spacing: 0;
}

.briefing-hero {
    background: linear-gradient(135deg, rgba(20,184,166,0.08), rgba(139,92,246,0.08));
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 20px;
    padding: clamp(1.35rem, 3vw, 2.5rem);
    margin: 1rem 0 1.5rem;
    overflow-wrap: anywhere;
}
.briefing-headline {
    font-size: clamp(1.7rem, 3.4vw, 2.65rem);
    font-weight: 900;
    line-height: 1.14;
    margin-top: 0.75rem;
    letter-spacing: 0;
    background: linear-gradient(135deg, #F3F6FA 0%, #14B8A6 52%, #8B5CF6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.briefing-copy {
    color: #8B949E;
    font-size: 1rem;
    margin-top: 1rem;
    line-height: 1.6;
    max-width: 980px;
}

.radar-row {
    display: flex;
    justify-content: space-between;
    gap: 1rem;
    align-items: flex-start;
}
.radar-title {
    font-size: 1.12rem;
    font-weight: 800;
    color: #F3F6FA;
    line-height: 1.35;
}
.radar-copy {
    color: #8B949E;
    font-size: 0.88rem;
    line-height: 1.55;
}
.radar-meta {
    color: #8B949E;
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 700;
}
.action-strip {
    margin-top: 0.85rem;
    padding: 0.65rem 0.8rem;
    background: rgba(20,184,166,0.08);
    border-radius: 8px;
    color: #14B8A6;
    font-size: 0.82rem;
    font-weight: 750;
}

[data-testid="stMetric"] {
    background: rgba(14, 17, 23, 0.6);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 12px;
    padding: 1rem;
}
[data-testid="stMetricValue"] {
    font-family: var(--font-mono) !important;
    font-weight: 800 !important;
}
[data-testid="stDataFrame"] {
    border: 1px solid #21262D;
    border-radius: 12px;
    overflow: hidden;
}
.radar-table-wrap {
    border: 1px solid #21262D;
    border-radius: 12px;
    overflow-x: auto;
    margin: 0.35rem 0 1rem;
}
.radar-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.86rem;
}
.radar-table th {
    color: #8B949E;
    text-align: left;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.68rem;
    background: #0E1117;
    padding: 0.7rem 0.8rem;
    border-bottom: 1px solid #21262D;
}
.radar-table td {
    color: #C9D1D9;
    padding: 0.72rem 0.8rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
    vertical-align: top;
}
.radar-table tr:last-child td {
    border-bottom: none;
}
.radar-table a {
    color: #38BDF8;
    text-decoration: none;
    font-weight: 750;
}
.radar-table a:hover {
    text-decoration: underline;
}
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #0E1117;
    border-radius: 12px;
    padding: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: 650;
    font-size: 0.8rem;
}
.stTabs [aria-selected="true"] {
    background: rgba(20, 184, 166, 0.15) !important;
    color: #14B8A6 !important;
}
[data-testid="stExpander"] {
    border: 1px solid #21262D;
    border-radius: 12px;
    background: rgba(14, 17, 23, 0.5);
}
.stDownloadButton > button,
.stButton > button {
    border-radius: 8px !important;
    font-weight: 650 !important;
}
.stDownloadButton > button {
    background: linear-gradient(135deg, #14B8A6, #0D9488) !important;
    color: white !important;
    border: none !important;
    transition: all 0.2s !important;
}
.stDownloadButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 4px 12px rgba(20, 184, 166, 0.3) !important;
}

[data-testid="stSidebar"] {
    background: #0E1117 !important;
    border-right: 1px solid #21262D !important;
}
[data-testid="stSidebar"],
[data-testid="stSidebar"] * {
    text-transform: uppercase !important;
}
[data-testid="stSidebar"] .stMarkdown h2 {
    font-size: 0.75rem !important;
    text-transform: uppercase !important;
    letter-spacing: 0.15em !important;
    color: #8B949E !important;
    margin-top: 1.5rem !important;
}

@media (max-width: 740px) {
    .radar-row { flex-direction: column; }
}
</style>
"""


def inject_custom_css(st_module: Any | None = None) -> None:
    if st_module is None:
        import streamlit as st_module

    st_module.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def _safe(value: Any) -> str:
    return escape(str(value or ""), quote=True)


_HTML_FRAGMENT_RE = re.compile(r"</?[a-zA-Z][\w:-]*(?:\s[^<>]*)?/?>")
_UNSAFE_STYLE_RE = re.compile(r"expression\s*\(|url\s*\(|javascript:|@import|behavior\s*:", re.I)
_INSIGHT_ALLOWED_TAGS = {
    "a",
    "b",
    "br",
    "code",
    "div",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "small",
    "span",
    "strong",
    "ul",
}
_INSIGHT_VOID_TAGS = {"br"}
_INSIGHT_DROP_CONTENT_TAGS = {"script", "style", "iframe", "object", "embed", "svg", "math"}
_INSIGHT_ALLOWED_ATTRS = {"class", "style", "href", "target", "rel"}
_INSIGHT_SAFE_HREF_PREFIXES = ("http://", "https://", "mailto:", "#", "/")


class _InsightHTMLSanitizer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in _INSIGHT_DROP_CONTENT_TAGS:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in _INSIGHT_ALLOWED_TAGS:
            return
        safe_attrs = self._safe_attrs(attrs)
        attr_html = f" {' '.join(safe_attrs)}" if safe_attrs else ""
        self.parts.append(f"<{tag}{attr_html}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _INSIGHT_VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _INSIGHT_DROP_CONTENT_TAGS and self._drop_depth:
            self._drop_depth -= 1
            return
        if self._drop_depth or tag not in _INSIGHT_ALLOWED_TAGS or tag in _INSIGHT_VOID_TAGS:
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:
        if self._drop_depth:
            return
        self.parts.append(escape(data, quote=False))

    def _safe_attrs(self, attrs: list[tuple[str, str | None]]) -> list[str]:
        safe_attrs = []
        for name, value in attrs:
            name = name.lower()
            value = str(value or "").strip()
            if name.startswith("on") or name not in _INSIGHT_ALLOWED_ATTRS or not value:
                continue
            if name == "href" and not value.lower().startswith(_INSIGHT_SAFE_HREF_PREFIXES):
                continue
            if name == "style":
                if _UNSAFE_STYLE_RE.search(value):
                    continue
            if name == "target" and value not in {"_blank", "_self"}:
                continue
            safe_attrs.append(f'{name}="{escape(value, quote=True)}"')
        return safe_attrs


def _insight_content_html(value: Any) -> str:
    text = str(value or "")
    if not _HTML_FRAGMENT_RE.search(text):
        return _safe(text)
    sanitizer = _InsightHTMLSanitizer()
    sanitizer.feed(text)
    sanitizer.close()
    return "".join(sanitizer.parts)


def verdict_html(verdict: str) -> str:
    value = str(verdict or "watch").upper().strip().replace("_", " ")
    if value in {"ACT NOW", "APPLY NOW", "URGENT"}:
        return f'<span class="verdict-act-now">{_safe(value)}</span>'
    if value in {"STRONG", "WATCH NOW", "HIGH", "READY"}:
        label = "STRONG" if value == "HIGH" else value
        return f'<span class="verdict-strong">{_safe(label)}</span>'
    if not value:
        value = "WATCH"
    return f'<span class="verdict-watch">{_safe(value)}</span>'


def pain_bar_html(level: int | float | str, max_level: int = 10) -> str:
    numeric = max(0, min(_coerce_int(level), max_level))
    pct = int(round((numeric / max(max_level, 1)) * 100))
    if numeric >= 7:
        cls = "pain-high"
    elif numeric >= 4:
        cls = "pain-medium"
    else:
        cls = "pain-low"
    return f"""
    <div style="display:flex;align-items:center;gap:8px;">
        <div class="pain-bar-track {cls}" style="flex:1;">
            <div class="pain-bar-fill" style="width:{pct}%;"></div>
        </div>
        <span style="font-family:var(--font-mono);font-weight:800;font-size:0.875rem;color:#F3F6FA;">{numeric}/{max_level}</span>
    </div>
    """


def source_status_html(status: str) -> str:
    value = str(status or "unknown")
    if value.startswith(("live", "ok")):
        cls = "status-live"
    elif value.startswith("fallback"):
        cls = "status-fallback"
    else:
        cls = "status-error"
    return f'<span class="{cls}">{_safe(value)}</span>'


def source_pills_html(sources: list[str]) -> str:
    return " ".join(f'<span class="source-pill">{_safe(source)}</span>' for source in sources[:6])


def section_header_html(title: str, detail: str = "") -> str:
    detail_html = f'<span style="color:#484F58;font-size:0.78rem;font-weight:700;margin-left:0.5rem;">{_safe(detail)}</span>' if detail else ""
    return f'<div class="section-header">{_safe(title)}{detail_html}</div>'


def glow_metric_html(label: str, value: str | int | float, glow: str = "teal", delta: str = "") -> str:
    glow = glow if glow in {"teal", "purple", "amber", "emerald", "rose", "sky", "orange"} else "teal"
    delta_html = ""
    if delta:
        delta_color = "#10B981" if str(delta).strip().startswith(("+", "ready", "live")) else "#F59E0B"
        delta_html = f'<div class="metric-delta" style="color:{delta_color};">{_safe(delta)}</div>'
    return f"""
    <div class="glow-card glow-{glow}">
        <div class="metric-label">{_safe(label)}</div>
        <div class="metric-value">{_safe(value)}</div>
        {delta_html}
    </div>
    """


def render_glow_metric(st_module: Any, label: str, value: str | int | float, glow: str = "teal", delta: str = "") -> None:
    st_module.markdown(glow_metric_html(label, value, glow=glow, delta=delta), unsafe_allow_html=True)


def briefing_hero_html(headline: str, narrative: str, act_now_count: int) -> str:
    alert_html = ""
    if act_now_count:
        alert_html = f'<div style="margin-top:1rem;">{verdict_html("ACT NOW")} <span style="color:#8B949E;font-size:0.86rem;margin-left:0.5rem;">{act_now_count} signals require action</span></div>'
    return f"""
    <div class="briefing-hero">
        <div class="micro-label">Morning Intelligence Briefing</div>
        <div class="briefing-headline">{_safe(headline)}</div>
        <div class="briefing-copy">{_safe(narrative)}</div>
        {alert_html}
    </div>
    """


def render_briefing_hero(st_module: Any, headline: str, narrative: str, act_now_count: int) -> None:
    st_module.markdown(briefing_hero_html(headline, narrative, act_now_count), unsafe_allow_html=True)


def idea_card_html(
    *,
    title: str,
    problem: str,
    quote: str,
    pain_level: int,
    complaints: int,
    score: int,
    sources: list[str],
    next_step: str,
    market: str = "",
    competition: str = "",
    index: int = 1,
) -> str:
    border_color = COLORS["rose"] if pain_level >= 7 else COLORS["orange"] if pain_level >= 4 else COLORS["amber"]
    market_bits = [f"{complaints} complaints"]
    if market:
        market_bits.append(f"{market} market")
    if competition:
        market_bits.append(f"{competition} competition")
    return f"""
    <div class="glass-card" style="border-left:3px solid {border_color};margin-bottom:1rem;">
        <div class="radar-row">
            <div>
                <div class="radar-meta">Gap #{index}</div>
                <div class="radar-title" style="margin-top:4px;">{_safe(title)}</div>
            </div>
        </div>
        <div class="radar-copy" style="margin-top:0.8rem;">{_safe(problem)}</div>
        <div style="margin-top:1rem;">{pain_bar_html(pain_level)}</div>
        <div style="margin-top:1rem;padding:0.8rem;background:rgba(255,255,255,0.03);border-radius:8px;border-left:2px solid #F59E0B;">
            <div class="micro-label" style="color:#F59E0B;">Evidence</div>
            <div style="font-style:italic;color:#C9D1D9;font-size:0.875rem;margin-top:0.25rem;">&quot;{_safe(quote)}&quot;</div>
        </div>
        <div class="radar-row" style="align-items:center;margin-top:0.9rem;">
            <div>{source_pills_html(sources)}</div>
            <div class="radar-copy" style="font-size:0.76rem;">{_safe(' | '.join(market_bits))}</div>
        </div>
        <div class="action-strip">Next: {_safe(next_step)}</div>
    </div>
    """


def render_idea_card(st_module: Any, **kwargs: Any) -> None:
    st_module.markdown(idea_card_html(**kwargs), unsafe_allow_html=True)


def signal_card_html(title: str, source: str, category: str, score: int, summary: str = "", url: str = "", action: str = "WATCH") -> str:
    title_html = (
        f'<a href="{_safe(url)}" target="_blank" rel="noopener noreferrer" style="color:#F3F6FA;text-decoration:none;">{_safe(title)}</a>'
        if url
        else _safe(title)
    )
    return f"""
    <div class="glass-card" style="margin-bottom:0.75rem;">
        <div class="radar-row">
            <div>
                <div class="radar-meta">{_safe(source)} | {_safe(category)}</div>
                <div class="radar-title" style="margin-top:4px;">{title_html}</div>
            </div>
        </div>
        <div class="radar-copy" style="margin-top:0.65rem;">{_safe(summary)}</div>
        <div class="radar-row" style="align-items:center;margin-top:0.8rem;">
            {verdict_html(action)}
        </div>
    </div>
    """


def alert_card_html(title: str, kind: str, score: int, body: str, channels: list[str]) -> str:
    return f"""
    <div class="glass-card" style="border-left:3px solid #EF4444;margin-bottom:0.8rem;">
        <div class="radar-row">
            <div>
                <div class="radar-meta">{_safe(kind)} | {_safe(', '.join(channels))}</div>
                <div class="radar-title" style="margin-top:4px;">{_safe(title)}</div>
            </div>
        </div>
        <div class="radar-copy" style="margin-top:0.75rem;">{_safe(body)}</div>
        <div style="margin-top:0.85rem;">{verdict_html("ACT NOW")}</div>
    </div>
    """


def insight_card_html(insight: dict[str, Any]) -> str:
    headline = insight.get("headline") or "Generated briefing insight"
    narrative = insight.get("narrative") or ""
    status = insight.get("status", "unknown")
    route = f"{insight.get('provider', 'unknown')}:{insight.get('model', 'unknown')}"
    columns = []
    for label, key, color in [
        ("Opportunities", "opportunities", "#10B981"),
        ("Risks", "risks", "#F43F5E"),
        ("Actions", "actions", "#14B8A6"),
    ]:
        items = list(insight.get(key, []) or [])[:4]
        body = "".join(f"<li>{_insight_content_html(item)}</li>" for item in items) or "<li>No items.</li>"
        columns.append(
            f'<div style="flex:1;min-width:180px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:0.9rem;">'
            f'<div class="micro-label" style="color:{color};">{label}</div>'
            f'<ul style="margin:0.55rem 0 0 1rem;padding:0;color:#C9D1D9;font-size:0.85rem;line-height:1.55;">{body}</ul>'
            "</div>"
        )
    return (
        '<div class="glass-card" style="margin-bottom:1rem;">'
        f'<div class="radar-meta">{_safe(status)} via {_safe(route)}</div>'
        f'<div class="radar-title" style="margin-top:0.45rem;">{_safe(headline)}</div>'
        f'<div class="radar-copy" style="margin-top:0.65rem;">{_insight_content_html(narrative)}</div>'
        f'<div style="display:flex;gap:0.8rem;flex-wrap:wrap;margin-top:1rem;">{"".join(columns)}</div>'
        "</div>"
    )


def project_detail_html(title: str, score: int, stars: Any, language: str, source: str, summary: str, action: str, url: str = "") -> str:
    title_html = (
        f'<a href="{_safe(url)}" target="_blank" rel="noopener noreferrer" style="color:#F3F6FA;text-decoration:none;">{_safe(title)}</a>'
        if url
        else _safe(title)
    )
    return f"""
    <div class="glass-card" style="margin-top:1rem;">
        <div class="radar-row">
            <div>
                <div class="radar-meta">{_safe(source)} | {_safe(language or 'unknown')}</div>
                <div class="radar-title" style="font-size:1.25rem;margin-top:4px;">{title_html}</div>
            </div>
        </div>
        <div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:0.9rem;">
            <span class="source-pill">Stars: {_safe(stars)}</span>
            <span class="source-pill">Language: {_safe(language or 'unknown')}</span>
            <span class="source-pill">{_safe(source)}</span>
        </div>
        <div class="radar-copy" style="margin-top:0.9rem;">{_safe(summary)}</div>
        <div class="action-strip">{_safe(action)}</div>
    </div>
    """


def radar_bar_chart(df: pd.DataFrame, x_col: str, y_col: str, color: str = "#14B8A6", title: str = "") -> go.Figure:
    fig = go.Figure(
        go.Bar(
            x=df[x_col] if x_col in df else [],
            y=df[y_col] if y_col in df else [],
            marker=dict(color=color, line=dict(width=0)),
            opacity=0.86,
        )
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color=COLORS["text_secondary"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color=COLORS["text_secondary"], size=12),
        xaxis=dict(gridcolor=COLORS["border_subtle"], linecolor=COLORS["border_subtle"], tickfont=dict(color=COLORS["text_secondary"])),
        yaxis=dict(gridcolor=COLORS["border_subtle"], linecolor=COLORS["border_subtle"], tickfont=dict(color=COLORS["text_secondary"])),
        margin=dict(l=40, r=20, t=40, b=40),
        height=280,
        bargap=0.28,
        showlegend=False,
    )
    return fig


def velocity_sparkline(dates: list[Any], values: list[Any], color: str = "#14B8A6", title: str = "") -> go.Figure:
    fill = _hex_to_rgba(color, 0.12)
    fig = go.Figure(
        go.Scatter(
            x=dates,
            y=values,
            mode="lines",
            fill="tozeroy",
            line=dict(color=color, width=2.5, shape="spline"),
            fillcolor=fill,
        )
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=12, color=COLORS["text_secondary"])),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color=COLORS["text_secondary"], size=12),
        xaxis=dict(showgrid=False, showticklabels=True, linecolor=COLORS["border_subtle"]),
        yaxis=dict(showgrid=True, gridcolor=COLORS["border_subtle"], linecolor=COLORS["border_subtle"]),
        margin=dict(l=30, r=10, t=30, b=30),
        height=200,
        showlegend=False,
    )
    return fig


def _hex_to_rgba(color: str, alpha: float) -> str:
    color = color.lstrip("#")
    if len(color) != 6:
        color = "14B8A6"
    red = int(color[0:2], 16)
    green = int(color[2:4], 16)
    blue = int(color[4:6], 16)
    return f"rgba({red},{green},{blue},{alpha})"


def _coerce_int(value: int | float | str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0
