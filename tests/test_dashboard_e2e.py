from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_streamlit_app_renders_all_tabs_without_exceptions():
    app = AppTest.from_file("dashboard/app.py", default_timeout=60)
    app.run()

    assert len(app.exception) == 0
    assert [title.value for title in app.title] == ["Internet Radar v2"]
    assert [(metric.label, metric.value) for metric in app.metric][:4] == [
        ("Active sources", "1"),
        ("Signals", "9"),
        ("Registered sources", "66"),
        ("Enabled by default", "46"),
    ]
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
