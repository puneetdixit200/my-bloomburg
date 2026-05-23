from __future__ import annotations

from internet_radar.storage.models import SignalRecord, UserProfile


def _signals() -> list[SignalRecord]:
    return [
        SignalRecord(
            id="social",
            topic="browser agents",
            title="Users complain browser agents are hard to debug",
            source="Reddit JSON",
            category="social",
            score=86,
            velocity=44,
            summary="Broken browser automation workflows and manual setup pain.",
            metadata={"frustration_score": 88},
        ),
        SignalRecord(
            id="code",
            topic="browser agents",
            title="Browser agent repos spike",
            source="GitHub Search",
            category="code",
            score=84,
            velocity=120,
            summary="Open-source browser automation agents are gaining stars.",
        ),
        SignalRecord(
            id="research",
            topic="browser agents",
            title="Agentic browser automation papers increase",
            source="arXiv",
            category="research",
            score=80,
            velocity=14,
            metadata={"citations": 32, "repo_stars": 120},
        ),
        SignalRecord(
            id="funding",
            topic="browser agents",
            title="Agent devtools startup funded",
            source="YC Companies",
            category="finance",
            score=78,
            metadata={"amount": 7_500_000, "investors": ["YC", "Accel"], "days_ago": 9},
        ),
    ]


def test_summarizer_builds_actionable_local_brief():
    from internet_radar.brain.llm_router import LLMRouter
    from internet_radar.brain.summarizer import summarize_signals

    summary = summarize_signals(_signals(), query="browser agents", router=LLMRouter(available_models=["qwen2.5:0.5b"]))

    assert summary.query == "browser agents"
    assert summary.route.provider == "ollama"
    assert "4 signals" in summary.headline
    assert summary.top_sources == ["Reddit JSON", "GitHub Search", "arXiv", "YC Companies"]
    assert summary.key_points[0].startswith("Top signal:")
    assert summary.next_action.startswith("Validate browser agents")


def test_classifier_tags_signal_with_keywords_and_route():
    from internet_radar.brain.classifier import classify_signal
    from internet_radar.brain.llm_router import LLMRouter

    classification = classify_signal(_signals()[0], router=LLMRouter(available_models=[]), allow_network=False)

    assert classification.topic == "browser agents"
    assert classification.sentiment == "negative"
    assert classification.category == "social"
    assert "browser agents" in classification.keywords
    assert classification.route.provider == "deterministic"
    assert classification.confidence >= 70


def test_gap_analyzer_turns_complaints_into_startup_ideas():
    from internet_radar.brain.gap_analyzer import analyze_gaps
    from internet_radar.brain.llm_router import LLMRouter

    extra = SignalRecord(
        id="hn",
        topic="browser agents",
        title="Ask HN: why are browser agents painful to debug?",
        source="Hacker News",
        category="social",
        score=82,
        summary="Developers complain about brittle setup and opaque failures.",
        metadata={"frustration_score": 92},
    )

    analyses = analyze_gaps([*_signals(), extra], router=LLMRouter(available_models=[]))

    assert analyses[0].topic == "browser agents"
    assert analyses[0].route.provider == "groq"
    assert analyses[0].patterns[0].complaints >= 2
    assert analyses[0].startup_ideas[0].market_size in {"medium", "large"}
    assert analyses[0].build_first is True


def test_trend_predictor_estimates_phase_and_timing():
    from internet_radar.brain.llm_router import LLMRouter
    from internet_radar.brain.trend_predictor import predict_trend

    prediction = predict_trend("browser agents", _signals(), router=LLMRouter(available_models=["qwen2.5:0.5b"]))

    assert prediction.topic == "browser agents"
    assert prediction.phase in {"emerging", "accelerating"}
    assert prediction.mainstream_months <= 12
    assert prediction.confidence >= 75
    assert prediction.best_time_to_learn == "now"
    assert prediction.route.provider == "ollama"


def test_idea_validator_scores_market_evidence():
    from internet_radar.brain.idea_validator import validate_idea
    from internet_radar.brain.llm_router import LLMRouter

    validation = validate_idea(
        "Browser agent debugging copilot",
        _signals(),
        profile=UserProfile(skills=["python", "playwright"]),
        router=LLMRouter(available_models=[]),
    )

    assert validation.idea == "Browser agent debugging copilot"
    assert validation.score >= 80
    assert validation.market_validation == "strong"
    assert "funding" in validation.evidence
    assert validation.recommendation == "build prototype"


def test_dashboard_payload_exposes_brain_outputs():
    from internet_radar.dashboard_data import build_dashboard_payload

    payload = build_dashboard_payload(_signals(), profile=UserProfile(skills=["python"]))

    assert payload["briefing"]["signal_summary"].query == "all signals"
    assert payload["briefing"]["classifications"][0].topic == "browser agents"
    assert payload["startup_gaps"]["gap_analyses"][0].topic == "browser agents"
    assert payload["trend_velocity"]["trend_predictions"][0].topic == "browser agents"
    assert payload["startup_gaps"]["idea_validations"][0].market_validation in {"moderate", "strong"}


def test_prompt_templates_keep_architecture_contracts():
    from internet_radar.brain.prompts import PROMPTS

    assert {"STARTUP_GAP", "TREND_VELOCITY", "DAILY_BRIEFING", "SKILL_RADAR", "HACKATHON_ANALYSIS"} <= set(PROMPTS)
    assert "Return ONLY valid JSON" in PROMPTS["STARTUP_GAP"]
    assert "{github_velocity}" in PROMPTS["TREND_VELOCITY"]
    assert "Max 400 words" in PROMPTS["DAILY_BRIEFING"]
    assert "Which 3 skills" in PROMPTS["SKILL_RADAR"]
