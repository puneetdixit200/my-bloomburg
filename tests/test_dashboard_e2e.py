from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_all_tabs_without_exceptions(tmp_path, monkeypatch):
    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))

    app = AppTest.from_file("dashboard/app.py", default_timeout=60)
    app.run()

    assert len(app.exception) == 0
    assert [title.value for title in app.title] == ["Internet Radar v2"]
    markdown = "\n".join(item.value for item in app.markdown)
    assert "glow-card glow-teal" in markdown
    assert "Active Sources" in markdown
    assert "briefing-hero" in markdown
    assert "score-badge" not in markdown
    assert "radar-table" in markdown
    assert "section-header" in markdown
    assert [tab.label for tab in app.tabs] == [
        "Morning Intelligence Briefing",
        "GitHub Radar",
        "Hackathon Radar",
        "Internship Radar",
        "Startup Gap Finder",
        "Multi-Source Trend Velocity",
        "Research Radar",
        "Funding Radar",
        "Skill Radar",
        "Community Pulse",
        "App Store Pain Miner",
        "Radar Search",
        "Your Profile",
    ]
