from __future__ import annotations

from datetime import UTC, datetime

from internet_radar.storage.models import SignalRecord


def test_keyword_extractor_finds_terms_and_entities():
    from internet_radar.signals.keyword_extractor import extract_entities, extract_keywords

    text = (
        "Show HN: Browser agents using local LLMs and MCP servers. "
        "Browser automation developers keep mentioning Playwright and Ollama."
    )

    assert extract_keywords(text, limit=5)[:3] == ["browser agents", "local llms", "mcp servers"]
    assert extract_entities(text) == ["Browser", "HN", "LLMs", "MCP", "Playwright", "Ollama"]


def test_trend_correlator_promotes_cross_category_spikes():
    from internet_radar.signals.trend_correlator import correlate_trends

    signals = [
        SignalRecord(id="gh", topic="browser agents", title="Repo spike", source="GitHub", category="code", score=86, velocity=120),
        SignalRecord(id="hn", topic="browser agents", title="HN spike", source="Hacker News", category="social", score=78, velocity=80),
        SignalRecord(id="arxiv", topic="browser agents", title="Paper spike", source="arXiv", category="research", score=74, velocity=10),
        SignalRecord(id="solo", topic="css variables", title="CSS post", source="Dev.to", category="news", score=62, velocity=5),
    ]

    correlations = correlate_trends(signals)

    assert correlations[0].topic == "browser agents"
    assert correlations[0].sources == ["GitHub", "Hacker News", "arXiv"]
    assert correlations[0].categories == ["code", "social", "research"]
    assert correlations[0].verdict == "STRONG"
    assert correlations[0].score >= 90
    assert all(correlation.topic != "css variables" for correlation in correlations)


def test_academic_signal_turns_research_records_into_future_demand():
    from internet_radar.signals.academic_signal import build_academic_signals

    records = [
        SignalRecord(
            id="arxiv",
            topic="agentic browser automation",
            title="Agentic browser automation papers increase",
            source="arXiv",
            category="research",
            score=77,
            velocity=14,
            metadata={"published_at": "2026-05-21T00:00:00Z"},
        ),
        SignalRecord(
            id="openalex",
            topic="agentic browser automation",
            title="Highly cited browser automation work",
            source="OpenAlex",
            category="research",
            score=82,
            velocity=55,
            metadata={"citations": 55, "institutions": ["MIT", "Stanford"]},
        ),
        SignalRecord(
            id="pwc",
            topic="agentic browser automation",
            title="Code for browser automation agents",
            source="Papers With Code",
            category="research",
            score=80,
            velocity=300,
            metadata={"repo_stars": 300},
        ),
    ]

    signals = build_academic_signals(records, now=datetime(2026, 5, 23, tzinfo=UTC))

    assert signals[0].topic == "agentic browser automation"
    assert signals[0].papers_per_week == 3
    assert signals[0].citation_velocity == 55
    assert signals[0].top_institution_count == 2
    assert signals[0].has_code_repos is True
    assert signals[0].industry_lag_months == "12-18"
    assert signals[0].score >= 85


def test_funding_signal_combines_money_with_hiring_validation():
    from internet_radar.signals.funding_signal import build_funding_signals

    records = [
        SignalRecord(
            id="yc",
            topic="ai devtools",
            title="AgentOps YC company signal",
            source="YC Companies",
            category="finance",
            score=76,
            metadata={"amount": 7_500_000, "investors": ["YC", "Accel"], "days_ago": 8},
        ),
        SignalRecord(
            id="jobs",
            topic="ai devtools",
            title="AI devtools hiring wave",
            source="RemoteOK",
            category="jobs",
            score=80,
            metadata={"related_jobs": 6},
        ),
    ]

    signals = build_funding_signals(records)

    assert signals[0].topic == "ai devtools"
    assert signals[0].amount == 7_500_000
    assert signals[0].related_jobs == 6
    assert signals[0].market_validation == "high"
    assert signals[0].score >= 85


def test_crowd_predictor_labels_apply_window_before_hackathon_crowds():
    from internet_radar.signals.crowd_predictor import predict_crowd

    prediction = predict_crowd(
        {
            "title": "NVIDIA AI Challenge",
            "current_participants": 40,
            "daily_growth": 9,
            "days_left": 6,
            "capacity": 180,
        }
    )

    assert prediction.projected_participants == 94
    assert prediction.crowd_ratio == 0.52
    assert prediction.recommendation == "APPLY NOW"
    assert prediction.alert == "crowd building but still favorable"


def test_dashboard_payload_exposes_architecture_signal_layers():
    from internet_radar.dashboard_data import build_dashboard_payload

    signals = [
        SignalRecord(id="gh", topic="browser agents", title="Browser agents repo spike", source="GitHub", category="code", score=86, velocity=120),
        SignalRecord(id="hn", topic="browser agents", title="Show HN: Browser agents", source="Hacker News", category="social", score=78, velocity=80),
        SignalRecord(
            id="arxiv",
            topic="browser agents",
            title="Browser agents paper spike",
            source="arXiv",
            category="research",
            score=77,
            velocity=12,
            metadata={"citations": 30, "institutions": ["MIT"], "repo_stars": 120},
        ),
        SignalRecord(
            id="funding",
            topic="ai devtools",
            title="AI devtools seed round",
            source="YC Companies",
            category="finance",
            score=76,
            metadata={"amount": 7_500_000, "investors": ["YC", "Accel"], "days_ago": 7},
        ),
        SignalRecord(
            id="hack",
            topic="ai challenge",
            title="NVIDIA AI Challenge",
            source="Devpost",
            category="hackathons",
            score=81,
            metadata={"current_participants": 40, "daily_growth": 9, "days_left": 6, "capacity": 180},
        ),
    ]

    payload = build_dashboard_payload(signals)

    assert payload["trend_velocity"]["trend_correlations"][0].topic == "browser agents"
    assert payload["research_radar"]["academic_signals"][0].topic == "browser agents"
    assert payload["funding_radar"]["funding_signals"][0].topic == "ai devtools"
    assert payload["hackathon_radar"]["crowd_predictions"][0].recommendation == "APPLY NOW"
