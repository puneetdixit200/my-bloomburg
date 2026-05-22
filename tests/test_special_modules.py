from __future__ import annotations

from datetime import UTC, datetime


def test_dead_tool_detector_finds_abandoned_repos():
    from internet_radar.special.radar import detect_dead_tools

    signals = detect_dead_tools(
        [
            {
                "full_name": "old/tool",
                "stargazers_count": 4200,
                "pushed_at": "2025-01-01T00:00:00Z",
                "open_issues_count": 184,
                "html_url": "https://github.com/old/tool",
            },
            {
                "full_name": "active/tool",
                "stargazers_count": 9000,
                "pushed_at": "2026-05-01T00:00:00Z",
                "open_issues_count": 300,
            },
        ],
        stale_before=datetime(2025, 12, 1, tzinfo=UTC),
    )

    assert len(signals) == 1
    assert signals[0].topic == "old/tool"
    assert signals[0].source == "Dead Tool Detector"
    assert signals[0].metadata["opportunity"] == "abandoned with active user base"
    assert signals[0].score >= 80


def test_conference_radar_extracts_future_topics():
    from internet_radar.special.radar import extract_conference_topics

    signals = extract_conference_topics(
        [
            {
                "title": "NeurIPS Workshop: Agentic AI for Browser Automation",
                "link": "https://neurips.cc/workshop",
                "summary": "Autonomous web agents, local LLM tooling, and safety.",
            },
            {
                "title": "ICLR Tutorial: Retrieval Agents",
                "link": "https://iclr.cc/tutorial",
                "summary": "RAG and agent evaluation.",
            },
        ]
    )

    assert signals[0].source == "Conference Radar"
    assert signals[0].category == "research"
    assert signals[0].topic == "agentic ai"
    assert "browser automation" in signals[0].metadata["keywords"]


def test_salary_tracker_scores_high_salary_skills():
    from internet_radar.special.radar import track_salary_velocity

    signals = track_salary_velocity(
        [
            {
                "title": "Machine Learning Engineer salaries",
                "href": "https://levels.fyi/ml",
                "body": "Machine learning engineer compensation now ranges from $180k to $260k, up 28% this year.",
            },
            {
                "title": "Frontend Developer salaries",
                "href": "https://levels.fyi/frontend",
                "body": "Frontend developer compensation ranges from $95k to $140k.",
            },
        ]
    )

    assert signals[0].topic == "machine learning engineer"
    assert signals[0].source == "Salary Signal Tracker"
    assert signals[0].category == "jobs"
    assert signals[0].metadata["salary_midpoint"] == 220000
    assert signals[0].score > signals[1].score


def test_wave_predictor_finds_early_mover_window():
    from internet_radar.special.radar import predict_next_waves

    signals = predict_next_waves(
        {
            "browser agents": {
                "arxiv": "active",
                "github": "active",
                "hackernews": "active",
                "reddit": "quiet",
                "linkedin": "quiet",
                "youtube": "quiet",
                "jobs": "quiet",
            },
            "bootcamp ai": {
                "arxiv": "active",
                "github": "active",
                "reddit": "active",
                "linkedin": "active",
                "jobs": "active",
            },
        }
    )

    assert len(signals) == 1
    assert signals[0].topic == "browser agents"
    assert signals[0].source == "Wave Predictor"
    assert signals[0].metadata["wave_position"] == "EARLY - ACT NOW"
    assert signals[0].score >= 90


def test_special_intelligence_collector_feeds_pipeline(tmp_path):
    from internet_radar.collectors.live import SpecialIntelligenceCollector
    from internet_radar.pipeline import run_radar_once

    result = run_radar_once(
        collectors=[SpecialIntelligenceCollector()],
        db_path=tmp_path / "radar.sqlite",
        use_live_network=False,
    )

    sources = {signal.source for signal in result.top_signals}
    assert {
        "Dead Tool Detector",
        "Conference Radar",
        "Salary Signal Tracker",
        "Wave Predictor",
    } <= sources
