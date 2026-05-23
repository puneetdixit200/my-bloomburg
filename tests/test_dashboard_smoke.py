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

    assert list(frame.columns) == ["score", "title", "source", "category", "url"]
    assert len(frame) == 5
    assert list(empty.columns) == ["score", "title", "source", "category", "url"]
    assert empty.empty
