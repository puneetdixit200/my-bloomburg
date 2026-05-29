from __future__ import annotations


def test_dashboard_has_all_architecture_pages():
    from internet_radar.dashboard_data import PAGE_DEFINITIONS

    assert len(PAGE_DEFINITIONS) == 12
    assert [page.key for page in PAGE_DEFINITIONS] == [
        "briefing",
        "github_radar",
        "hackathon_radar",
        "startup_gaps",
        "trend_velocity",
        "research_radar",
        "funding_radar",
        "skill_radar",
        "community_pulse",
        "app_store_pain",
        "radar_search",
        "profile",
    ]


def test_dashboard_payload_groups_signals_by_page():
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.storage.models import SignalRecord

    payload = build_dashboard_payload(
        [
            SignalRecord(id="gh:1", topic="mcp", title="MCP repo spike", source="GitHub", category="code", score=91),
            SignalRecord(id="job:1", topic="ai intern", title="AI internship", source="RemoteOK", category="jobs", score=80),
            SignalRecord(id="paper:1", topic="agents", title="Agent paper", source="arXiv", category="research", score=77),
        ],
        active_sources=9,
    )

    assert payload["briefing"]["active_sources"] == 9
    assert payload["github_radar"]["signals"][0].source == "GitHub"
    assert "internship_radar" not in payload
    assert payload["research_radar"]["signals"][0].category == "research"
    assert "collection" in payload["briefing"]


def test_sample_payload_has_hackathon_radar_signal(tmp_path):
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.pipeline import run_radar_once

    briefing = run_radar_once(db_path=tmp_path / "radar.sqlite", use_live_network=False)
    payload = build_dashboard_payload(briefing.top_signals, active_sources=briefing.active_sources)

    assert payload["hackathon_radar"]["signals"]
    assert payload["hackathon_radar"]["signals"][0].category == "hackathons"


def test_dashboard_database_recheck_payload_reads_sqlite_signals(tmp_path):
    from datetime import UTC, datetime, timedelta

    from dashboard.app import _payload_from_database
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.models import SignalRecord

    db_path = tmp_path / "radar.sqlite"
    deadline = (datetime.now(UTC) + timedelta(days=7)).date().isoformat()
    store = RadarStore(db_path)
    store.upsert_signals(
        [
            SignalRecord(
                id="hack",
                topic="student hackathon",
                title="Student AI Hackathon",
                source="Devpost",
                category="hackathons",
                score=88,
                metadata={"deadline": deadline},
            ),
            SignalRecord(id="repo", topic="mcp", title="MCP repo", source="GitHub", category="code", score=84),
        ]
    )

    payload = _payload_from_database(db_path=db_path, limit=50)

    assert payload["hackathon_radar"]["signals"][0].title == "Student AI Hackathon"
    assert payload["github_radar"]["signals"][0].title == "MCP repo"
    assert payload["briefing"]["collection"]["mode"] == "live"
    assert payload["briefing"]["source_counts"] == {"Devpost": 1, "GitHub": 1}


def test_dashboard_database_recheck_filters_expired_and_stale_signals(tmp_path, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from dashboard.app import _payload_from_database
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.models import SignalRecord

    db_path = tmp_path / "radar.sqlite"
    now = datetime.now(UTC)
    store = RadarStore(db_path)
    store.upsert_signals(
        [
            SignalRecord(
                id="old",
                topic="old hackathon",
                title="Old Hackathon",
                source="Crawler",
                category="hackathons",
                score=100,
                observed_at=now - timedelta(days=45),
            ),
            SignalRecord(
                id="expired",
                topic="expired hackathon",
                title="Expired Hackathon",
                source="Crawler",
                category="hackathons",
                score=99,
                metadata={"deadline": (now - timedelta(days=1)).date().isoformat()},
            ),
            SignalRecord(
                id="missing-deadline",
                topic="unknown hackathon",
                title="Missing Deadline Hackathon",
                source="Crawler",
                category="hackathons",
                score=98,
                observed_at=now,
            ),
            SignalRecord(
                id="fresh",
                topic="fresh hackathon",
                title="Fresh Hackathon",
                source="Crawler",
                category="hackathons",
                score=50,
                observed_at=now,
                metadata={"deadline": (now + timedelta(days=7)).date().isoformat()},
            ),
        ]
    )

    payload = _payload_from_database(db_path=db_path, limit=50)

    assert [signal.title for signal in payload["hackathon_radar"]["signals"]] == ["Fresh Hackathon"]
    assert all(prediction.recommendation != "EXPIRED" for prediction in payload["hackathon_radar"]["crowd_predictions"])
    assert payload["briefing"]["source_counts"] == {"Crawler": 1}


def test_streamlit_app_import_is_side_effect_safe():
    import dashboard.app as app

    assert callable(app.main)
    assert callable(app.render_dashboard)


def test_dashboard_theme_defines_premium_design_system_css():
    from dashboard.theme import COLORS, CUSTOM_CSS

    assert COLORS["bg_primary"] == "#0A0D12"
    assert COLORS["teal"] == "#14B8A6"
    for class_name in [
        ".glass-card",
        ".glow-card",
        ".radar-table",
        ".pain-bar-track",
        ".source-pill",
        ".status-live",
        ".status-fallback",
        ".status-error",
        ".verdict-act-now",
        ".section-header",
    ]:
        assert class_name in CUSTOM_CSS
    assert "Inter" in CUSTOM_CSS
    assert "JetBrains Mono" in CUSTOM_CSS
    assert "[data-testid=\"stSidebar\"]" in CUSTOM_CSS
    assert ".score-badge" not in CUSTOM_CSS


def test_dashboard_theme_html_helpers_classify_and_escape_values():
    from dashboard.theme import (
        briefing_hero_html,
        pain_bar_html,
        source_status_html,
        verdict_html,
    )

    assert "verdict-act-now" in verdict_html("ACT NOW")
    assert "verdict-strong" in verdict_html("STRONG")
    assert "verdict-watch" in verdict_html("WATCH")

    pain_html = pain_bar_html(8)
    assert "pain-high" in pain_html
    assert "width:80%" in pain_html

    assert "status-live" in source_status_html("live (12)")
    assert "status-fallback" in source_status_html("fallback (1)")
    assert "status-error" in source_status_html("error: timeout")

    hero = briefing_hero_html("<browser agents>", "Use <safe> output", 2)
    assert "&lt;browser agents&gt;" in hero
    assert "&lt;safe&gt;" in hero
    assert "2 signals require action" in hero


def test_llm_insight_card_renders_sanitized_html_fragments():
    from dashboard.theme import insight_card_html

    html = insight_card_html(
        {
            "status": "generated",
            "provider": "ollama",
            "model": "qwen2.5:0.5b",
            "headline": "Velocity Docker image",
            "narrative": '<div class="micro-label" onclick="alert(1)">Risks</div><script>alert(1)</script>',
            "opportunities": ["Use <strong>container orchestration</strong>"],
            "risks": ["Validate demand"],
            "actions": [
                '<div style="color:#14B8A6;">Explore the Velocity Docker image</div>',
            ],
        }
    )

    assert '<div class="micro-label">Risks</div>' in html
    assert "<strong>container orchestration</strong>" in html
    assert '<div style="color:#14B8A6;">Explore the Velocity Docker image</div>' in html
    assert "<script" not in html
    assert "onclick" not in html
    assert "&lt;strong&gt;" not in html
    assert not any(
        line.startswith("    ") and line.lstrip().startswith("<")
        for line in html.splitlines()
    )


def test_dashboard_theme_plotly_charts_use_dark_terminal_layout():
    import pandas as pd

    from dashboard.theme import radar_bar_chart, velocity_sparkline

    bar = radar_bar_chart(pd.DataFrame({"category": ["code"], "signals": [4]}), "category", "signals", title="Signal Distribution")
    sparkline = velocity_sparkline(["2026-05-25", "2026-05-26"], [70, 91], title="Velocity")

    assert bar.data[0].type == "bar"
    assert bar.layout.paper_bgcolor == "rgba(0,0,0,0)"
    assert bar.layout.plot_bgcolor == "rgba(0,0,0,0)"
    assert bar.layout.height == 280
    assert "Inter" in bar.layout.font.family
    assert sparkline.data[0].type == "scatter"
    assert sparkline.data[0].fill == "tozeroy"
    assert sparkline.layout.showlegend is False


def test_dashboard_app_wires_premium_css_metrics_and_plotly_charts():
    from pathlib import Path

    source = Path("dashboard/app.py").read_text()

    assert "inject_custom_css()" in source
    assert "render_glow_metric" in source
    assert "st.plotly_chart" in source
    assert "radar_bar_chart(" in source
    assert "render_idea_card(" in source
    assert "Free-only Guardrails" not in source


def test_dashboard_signal_filters_are_shared_across_pages():
    from dashboard.app import _apply_filters
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(id="code", topic="mcp", title="MCP repo spike", source="GitHub Search", category="code", score=91),
        SignalRecord(id="job", topic="ai intern", title="AI internship", source="RemoteOK", category="jobs", score=70),
    ]

    filtered = _apply_filters(signals, {"categories": ["code"], "min_score": 80, "query": "repo", "source": "GitHub Search"})
    group_filtered = _apply_filters(signals, {"source_groups": ["jobs"]})

    assert [signal.id for signal in filtered] == ["code"]
    assert [signal.id for signal in group_filtered] == ["job"]


def test_dashboard_page_metric_values_summarize_page_signals():
    from dashboard.app import _page_metric_values
    from internet_radar.storage.models import SignalRecord

    metrics = _page_metric_values(
        [
            SignalRecord(id="code", topic="mcp", title="MCP repo spike", source="GitHub Search", category="code", score=91),
            SignalRecord(id="job", topic="ai intern", title="AI internship", source="RemoteOK", category="jobs", score=70),
        ]
    )

    assert metrics == {
        "signals": 2,
        "sources": 2,
        "topics": 2,
        "categories": 2,
    }


def test_dashboard_extracts_project_signals_for_github_radar():
    from dashboard.app import _project_signals, _projects_to_frame
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(
            id="repo",
            topic="agent repo",
            title="example/agent",
            source="GitHub Search",
            category="code",
            url="https://github.com/example/agent",
            score=91,
            metadata={"stars": 123, "language": "Python"},
        ),
        SignalRecord(
            id="search",
            topic="agent search",
            title="Agent search",
            source="GitHub Search",
            category="code",
            url="https://github.com/search?q=agents",
            score=88,
        ),
        SignalRecord(id="pkg", topic="agent package", title="agent package", source="PyPI", category="code", score=80),
    ]

    projects = _project_signals(signals)
    frame = _projects_to_frame(projects)

    assert [signal.id for signal in projects] == ["repo"]
    assert frame.iloc[0]["project"] == "example/agent"
    assert frame.iloc[0]["stars"] == 123


def test_dashboard_signal_preview_frame_is_static_and_limited():
    from dashboard.app import _signal_preview_frame
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(id=str(index), topic="mcp", title=f"Signal {index}", source="GitHub Search", category="code", score=90 - index)
        for index in range(12)
    ]

    frame = _signal_preview_frame(signals, limit=5)
    empty = _signal_preview_frame([])

    assert list(frame.columns) == ["topic", "title", "source", "category", "summary", "url"]
    assert len(frame) == 5
    assert list(empty.columns) == ["topic", "title", "source", "category", "summary", "url"]
    assert empty.empty


def test_dashboard_signal_preview_balances_sources_and_embeds_links_in_topic():
    from dashboard.app import _prepare_visible_frame, _signal_table_column_config, _signal_preview_frame
    from internet_radar.storage.models import SignalRecord

    signals = [
        *[
            SignalRecord(
                id=f"crate-{index}",
                topic=f"crate {index}",
                title=f"crate {index}",
                source="crates.io",
                category="code",
                url=f"https://crates.io/crates/crate-{index}",
                score=100 - index,
            )
            for index in range(8)
        ],
        SignalRecord(id="gh", topic="mcp", title="MCP repo", source="GitHub Search", category="code", url="https://github.com/example/mcp", score=91),
        SignalRecord(id="pypi", topic="agent", title="agent package", source="PyPI", category="code", url="https://pypi.org/project/agent/", score=90),
        SignalRecord(id="news", topic="agents", title="Agent article", source="Dev.to", category="news", url="https://dev.to/example/agents", score=89),
        SignalRecord(id="docker", topic="agent", title="agent image", source="Docker Hub", category="code", url="https://hub.docker.com/r/example/agent", score=88),
    ]

    frame = _signal_preview_frame(signals, limit=6)
    column_config = _signal_table_column_config()

    assert len(frame) == 6
    assert list(frame["source"]).count("crates.io") <= 2
    assert {"GitHub Search", "PyPI", "Dev.to"} <= set(frame["source"])
    assert column_config == {}

    visible, has_links = _prepare_visible_frame(frame)
    assert has_links is True
    assert "url" not in visible.columns
    assert "score" not in visible.columns
    assert visible.iloc[0]["topic"].startswith('<a href="https://crates.io/crates/crate-0"')


def test_dashboard_public_payload_helpers_strip_scores_and_link_columns():
    from dashboard.app import (
        _export_visible_frame,
        _prepare_visible_frame,
        _public_json,
        _public_signal_json,
        _public_text,
        _signal_preview_frame,
    )
    from internet_radar.storage.models import SignalRecord

    signal = SignalRecord(
        id="gh",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        url="https://github.com/example/browser-agent",
        score=94,
        metadata={"relevance_score": 88, "stars": 1200},
    )
    frame, has_links = _prepare_visible_frame(_signal_preview_frame([signal]))
    exported = _export_visible_frame(_signal_preview_frame([signal]))

    assert has_links is True
    assert list(frame.columns) == ["topic", "title", "source", "category", "summary"]
    assert '<a href="https://github.com/example/browser-agent"' in frame.iloc[0]["topic"]
    assert "url" not in exported.columns
    assert not any("score" in str(column).lower() for column in exported.columns)

    public_signal = _public_signal_json(signal)
    assert "score" not in public_signal
    assert "relevance_score" not in public_signal["metadata"]
    assert "top score" not in _public_text("Daily summary with top score 94. Keep watching.").lower()
    assert _public_json({"score": 94, "nested": {"domain_score": 10, "note": "scored 94/100 today"}}) == {
        "nested": {"note": "today"}
    }


def test_radar_search_analysis_helpers_render_readable_tables():
    from dashboard.app import (
        _query_analysis_overview_frame,
        _query_deep_dive_frame,
        _query_top_results_frame,
    )
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(
            id="sig-1",
            topic="browser agents",
            title="Browser agents are easier to debug",
            source="GitHub Search",
            category="code",
            url="https://github.com/example/browser-agent",
            score=88,
        )
    ]
    analysis = {
        "browser agents": {
            "query": "browser agents",
            "matching_signals": 1,
            "source_count": 1,
            "top_categories": ["code"],
            "top_sources": ["GitHub Search"],
            "total_velocity": 1200,
            "personal_relevance": 76,
            "top_results": ["sig-1"],
            "deep_dive": {
                "executive_summary": "One strong developer tooling signal.",
                "opportunities": ["Build a debugging workflow"],
                "risks": ["Validate freshness"],
                "suggested_actions": ["Open the linked repo"],
            },
        }
    }

    overview = _query_analysis_overview_frame(analysis)
    deep_dive = _query_deep_dive_frame(analysis)
    top_results = _query_top_results_frame(analysis, signals)

    assert list(overview.columns) == ["query", "matches", "sources", "categories", "top_sources", "velocity", "personal_relevance"]
    assert overview.iloc[0]["categories"] == "code"
    assert "Build a debugging workflow" in deep_dive.iloc[0]["opportunities"]
    assert top_results.iloc[0]["topic"] == "browser agents"
    assert top_results.iloc[0]["url"] == "https://github.com/example/browser-agent"


def test_radar_search_page_does_not_dump_query_analysis_json():
    from pathlib import Path

    source = Path("dashboard/app.py").read_text()

    assert "st.json(_public_json(page_payload.get(\"query_analysis\"" not in source
    assert "_query_analysis_overview_frame" in source
    assert "_query_deep_dive_frame" in source


def test_dashboard_report_and_source_health_frames():
    from dashboard.app import _build_markdown_report, _source_health_frame
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.storage.models import SignalRecord

    payload = build_dashboard_payload(
        [SignalRecord(id="gh", topic="mcp", title="MCP repo spike", source="GitHub Search", category="code", score=91)],
        active_sources=1,
        source_health={"GitHub Search": "live (1)", "GDELT": "fallback (1)"},
        source_counts={"GitHub Search": 1},
        source_durations_seconds={"GitHub Search": 0.2},
        collection_mode="live",
    )

    report = _build_markdown_report(payload)
    health = _source_health_frame(payload["briefing"])

    assert "Internet Radar Daily Report" in report
    assert "MCP repo spike" in report
    assert set(health["mode"]) == {"live", "fallback"}
    assert "GitHub Search" in set(health["source"])
    assert int(health.loc[health["source"] == "GitHub Search", "signals"].iloc[0]) == 1


def test_dashboard_free_only_guardrails_show_paid_paths(monkeypatch):
    from dashboard.app import _free_only_guardrails_frame

    monkeypatch.setenv("INTERNET_RADAR_FREE_ONLY", "1")
    free_only_frame = _free_only_guardrails_frame()

    assert list(free_only_frame["integration"]) == ["Brave Search API", "Crunchbase API", "Mailgun Email"]
    assert set(free_only_frame["status"]) == {"disabled"}
    assert all("free-only" in reason for reason in free_only_frame["reason"])

    monkeypatch.setenv("INTERNET_RADAR_FREE_ONLY", "0")
    configured_frame = _free_only_guardrails_frame()

    assert set(configured_frame["status"]) == {"credential-gated"}


def test_dashboard_objects_frame_preserves_pipeline_dict_artifacts():
    from dashboard.app import _objects_to_frame

    frame = _objects_to_frame(
        [
            {"topic": "browser agents", "confidence": 91},
            {"topic": "local llm", "confidence": 84},
        ]
    )

    assert list(frame["topic"]) == ["browser agents", "local llm"]
    assert list(frame["confidence"]) == [91, 84]


def test_dashboard_alert_outbox_frame_shows_pending_and_sent_rows(tmp_path):
    from dashboard.app import _alert_outbox_frame
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    outbox = AlertOutbox(tmp_path / "radar.sqlite")
    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )
    item_id = outbox.enqueue(alert, channel="ntfy", detail="network error: Timeout")
    outbox._mark_result(item_id, AlertDispatchResult(channel="ntfy", sent=True, detail="sent"))

    frame = _alert_outbox_frame(tmp_path / "radar.sqlite")

    assert list(frame["signal_id"]) == ["skill-1"]
    assert list(frame["status"]) == ["sent"]
    assert list(frame["channel"]) == ["ntfy"]


def test_dashboard_make_real_readiness_frame_uses_current_payload_and_db(tmp_path, monkeypatch):
    from dashboard.app import _make_real_readiness_frame
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.models import SignalRecord

    db_path = tmp_path / "radar.sqlite"
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=92,
        metadata={"stars": 1200},
    )
    store = RadarStore(db_path)
    store.upsert_signals([signal])
    store.record_signal_snapshots([signal])
    monkeypatch.setenv("INTERNET_RADAR_DISPATCH_ALERTS", "1")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    signals = [
        signal.model_copy(update={"id": f"repo:agent-{index}", "title": f"Browser agent repo {index}"})
        for index in range(120)
    ]
    payload = build_dashboard_payload(
        signals,
        active_sources=67,
        llm_status="ollama:qwen2.5:0.5b",
        collection_mode="live",
        source_health={"Reddit JSON": "live (40)"},
        analysis_artifacts={"llm_generated_insight": {"status": "generated", "provider": "ollama", "model": "qwen2.5:0.5b"}},
    )

    frame = _make_real_readiness_frame(payload["briefing"], db_path=db_path)

    statuses = dict(zip(frame["key"], frame["status"], strict=False))
    assert statuses["time_series"] == "ready"
    assert statuses["live_collection"] == "ready"
    assert statuses["reddit_json"] == "ready"
    assert statuses["reddit_oauth"] == "blocked"
