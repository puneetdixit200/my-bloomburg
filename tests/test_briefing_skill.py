from __future__ import annotations

from internet_radar.storage.models import SignalRecord, UserProfile


def test_briefing_writer_builds_architecture_sections():
    from internet_radar.brain.briefing_writer import write_daily_briefing

    signals = [
        SignalRecord(
            id="trend:1",
            topic="browser agents",
            title="Browser agents jump across GitHub and HN",
            source="GitHub",
            category="code",
            score=94,
            velocity=62,
        ),
        SignalRecord(
            id="job:1",
            topic="browser agents",
            title="AI browser automation intern",
            source="RemoteOK",
            category="jobs",
            score=87,
            velocity=25,
        ),
        SignalRecord(
            id="paper:1",
            topic="local llm agents",
            title="Local LLM agent planning paper",
            source="arXiv",
            category="research",
            score=78,
            velocity=18,
        ),
    ]

    briefing = write_daily_briefing(signals, active_sources=9, llm_status="ollama:qwen2.5:0.5b")

    assert briefing["headline"] == "browser agents"
    assert briefing["metrics"] == {"active_sources": 9, "signals_24h": 3, "llm_status": "ollama:qwen2.5:0.5b"}
    assert briefing["act_now"][0]["title"] == "Browser agents jump across GitHub and HN"
    assert briefing["job_market"][0]["source"] == "RemoteOK"
    assert briefing["research"][0]["topic"] == "local llm agents"
    assert briefing["narrative"].startswith("Browser agents is the top signal")


def test_skill_recommender_combines_market_and_research_signals():
    from internet_radar.brain.skill_recommender import recommend_skills

    profile = UserProfile(skills=["python"], interests=["agents"])
    signals = [
        SignalRecord(
            id="job:1",
            topic="browser agents",
            title="Browser automation intern needs Playwright",
            source="RemoteOK",
            category="jobs",
            score=92,
            velocity=30,
            metadata={"skills": ["playwright", "python"]},
        ),
        SignalRecord(
            id="repo:1",
            topic="browser agents",
            title="Playwright agent framework stars explode",
            source="GitHub",
            category="code",
            score=88,
            velocity=45,
            metadata={"skills": ["playwright", "typescript"]},
        ),
        SignalRecord(
            id="paper:1",
            topic="browser agents",
            title="Browser agent benchmark",
            source="arXiv",
            category="research",
            score=75,
            velocity=15,
            metadata={"skills": ["playwright"]},
        ),
    ]

    recommendations = recommend_skills(signals, profile=profile, limit=3)

    assert recommendations[0].skill == "playwright"
    assert recommendations[0].score > 90
    assert recommendations[0].demand_signals == 3
    assert recommendations[0].sources == ["RemoteOK", "GitHub", "arXiv"]
    assert recommendations[0].learning_path[0].startswith("Build")
    assert "python" not in [recommendation.skill for recommendation in recommendations]


def test_dashboard_payload_exposes_briefing_and_skill_recommendations():
    from internet_radar.dashboard_data import build_dashboard_payload

    signals = [
        SignalRecord(
            id="job:1",
            topic="local llm agents",
            title="Ollama agent internship",
            source="RemoteOK",
            category="jobs",
            score=90,
            metadata={"skills": ["ollama", "python"]},
        ),
        SignalRecord(
            id="repo:1",
            topic="local llm agents",
            title="Ollama agent toolkit",
            source="GitHub",
            category="code",
            score=84,
            metadata={"skills": ["ollama"]},
        ),
    ]

    payload = build_dashboard_payload(signals, active_sources=5, llm_status="deterministic fallback", profile=UserProfile(skills=["python"]))

    assert payload["briefing"]["daily_briefing"]["headline"] == "local llm agents"
    assert payload["skill_radar"]["skill_recommendations"][0].skill == "ollama"
