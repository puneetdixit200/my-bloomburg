from __future__ import annotations


def test_dashboard_has_all_architecture_pages():
    from internet_radar.dashboard_data import PAGE_DEFINITIONS

    assert len(PAGE_DEFINITIONS) == 13
    assert [page.key for page in PAGE_DEFINITIONS] == [
        "briefing",
        "github_radar",
        "hackathon_radar",
        "internship_radar",
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
    assert payload["internship_radar"]["signals"][0].category == "jobs"
    assert payload["research_radar"]["signals"][0].category == "research"


def test_sample_payload_has_hackathon_radar_signal(tmp_path):
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.pipeline import run_radar_once

    briefing = run_radar_once(db_path=tmp_path / "radar.sqlite", use_live_network=False)
    payload = build_dashboard_payload(briefing.top_signals, active_sources=briefing.active_sources)

    assert payload["hackathon_radar"]["signals"]
    assert payload["hackathon_radar"]["signals"][0].category == "hackathons"


def test_streamlit_app_import_is_side_effect_safe():
    import dashboard.app as app

    assert callable(app.main)
    assert callable(app.render_dashboard)


def test_dashboard_signal_filters_are_shared_across_pages():
    from dashboard.app import _apply_filters
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(id="code", topic="mcp", title="MCP repo spike", source="GitHub Search", category="code", score=91),
        SignalRecord(id="job", topic="ai intern", title="AI internship", source="RemoteOK", category="jobs", score=70),
    ]

    filtered = _apply_filters(signals, {"categories": ["code"], "min_score": 80, "query": "repo", "source": "GitHub Search"})

    assert [signal.id for signal in filtered] == ["code"]
