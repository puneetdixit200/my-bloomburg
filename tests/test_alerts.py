from __future__ import annotations

from internet_radar.storage.models import SignalRecord, UserProfile


def test_format_alert_uses_architecture_template_for_hackathon():
    from internet_radar.alerts.alert_manager import format_alert

    signal = SignalRecord(
        id="hack-1",
        topic="agent hackathon",
        title="NVIDIA AI Hack",
        source="Devpost",
        category="hackathons",
        url="https://example.com/hack",
        score=91,
        metadata={
            "prize": 50000,
            "participants": 67,
            "days_left": 12,
            "remote": True,
            "sponsors": ["NVIDIA"],
            "theme": "AI agents",
            "reasoning": "Strong sponsor fit and short deadline.",
        },
    )

    alert = format_alert(signal)

    assert alert.kind == "HACKATHON"
    assert alert.title == "HIGH OPPORTUNITY - HACKATHON"
    assert "NVIDIA AI Hack" in alert.body
    assert "Prize: $50,000" in alert.body
    assert "Deadline: 12 days" in alert.body
    assert "SCORE: 91/100" in alert.body
    assert "https://example.com/hack" in alert.body


def test_build_alerts_filters_by_profile_threshold_and_channels():
    from internet_radar.alerts.alert_manager import build_alerts

    profile = UserProfile(alert_threshold=80, notification_channels=["ntfy", "telegram"])
    hot = SignalRecord(
        id="skill-1",
        topic="mcp servers",
        title="MCP servers skill demand rising",
        source="Skill Radar",
        category="jobs",
        score=74,
        metadata={"relevance_score": 88, "skill": "MCP servers", "job_growth": 280},
    )
    cold = SignalRecord(id="cold-1", topic="frontend", title="CSS library", source="Dev.to", category="news", score=70)

    alerts = build_alerts([cold, hot], profile)

    assert len(alerts) == 1
    assert alerts[0].signal_id == "skill-1"
    assert alerts[0].kind == "SKILL_RADAR"
    assert alerts[0].channels == ["ntfy", "telegram"]
    assert "Skill: MCP servers" in alerts[0].body


def test_format_alert_supports_research_funding_and_gap_templates():
    from internet_radar.alerts.alert_manager import format_alert

    research = format_alert(
        SignalRecord(
            id="research-1",
            topic="embodied ai",
            title="Embodied AI papers increase",
            source="arXiv",
            category="research",
            score=82,
            metadata={"papers_week": 18, "growth": 340, "recommended_skill": "robotics simulation"},
        )
    )
    funding = format_alert(
        SignalRecord(
            id="funding-1",
            topic="ai devtools",
            title="Code agents startup raises seed",
            source="YC",
            category="finance",
            score=86,
            metadata={"company": "Code Agents", "amount": 4_700_000, "sector": "developer tools"},
        )
    )
    gap = format_alert(
        SignalRecord(
            id="gap-1",
            topic="ai resume tools",
            title="Users complain about resume tools",
            source="Reddit JSON",
            category="social",
            score=84,
            metadata={"pain_level": 9, "complaint_count": 234, "best_quote": "Too much manual editing."},
        )
    )

    assert research.kind == "RESEARCH_SIGNAL"
    assert "SKILL TO LEARN: robotics simulation" in research.body
    assert funding.kind == "FUNDING_ALERT"
    assert "Amount: $4,700,000" in funding.body
    assert gap.kind == "STARTUP_GAP"
    assert "Complaints found: 234" in gap.body


def test_dashboard_payload_includes_profile_threshold_alerts():
    from internet_radar.dashboard_data import build_dashboard_payload

    profile = UserProfile(alert_threshold=85, notification_channels=["ntfy"])
    signal = SignalRecord(
        id="hack-2",
        topic="agent hackathon",
        title="Agent Hack",
        source="Devpost",
        category="hackathons",
        score=82,
        metadata={"relevance_score": 93, "prize": 10000, "days_left": 5},
    )

    payload = build_dashboard_payload([signal], active_sources=1, profile=profile)

    assert payload["briefing"]["alerts"][0].signal_id == "hack-2"
    assert payload["briefing"]["alerts"][0].channels == ["ntfy"]
    assert payload["briefing"]["alerts"][0].score == 93
