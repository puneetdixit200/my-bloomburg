from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_load_user_profile_from_yaml(tmp_path):
    from internet_radar.config.settings import load_user_profile

    profile_file = tmp_path / "interests.yaml"
    profile_file.write_text(
        """
profile:
  skills: [python, ai]
  interests: [browser agents, mcp]
  goals: [find internships]
  blocked_topics: [crypto]
  alert_threshold: 75
""",
        encoding="utf-8",
    )

    profile = load_user_profile(profile_file)

    assert profile.skills == ["python", "ai"]
    assert profile.interests == ["browser agents", "mcp"]
    assert profile.alert_threshold == 75
    assert profile.blocked_topics == ["crypto"]


def test_relevance_scorer_boosts_profile_matches_and_blocks_topics():
    from internet_radar.brain.relevance_scorer import rank_for_profile, score_signal_relevance
    from internet_radar.storage.models import UserProfile

    profile = UserProfile(
        skills=["python", "automation"],
        interests=["browser agents"],
        goals=["find internships"],
        blocked_topics=["crypto"],
    )
    matching = SignalRecord(
        id="match",
        topic="browser agents",
        title="Python browser automation internship",
        source="RemoteOK",
        category="jobs",
        score=70,
        summary="Build local AI automation agents.",
    )
    blocked = SignalRecord(id="blocked", topic="crypto", title="Crypto trading bot", source="HN", category="social", score=99)

    relevance = score_signal_relevance(matching, profile)
    ranked = rank_for_profile([blocked, matching], profile)

    assert relevance.score >= 85
    assert "interest:browser agents" in relevance.reasons
    assert "skill:python" in relevance.reasons
    assert ranked == [matching]
    assert ranked[0].metadata["relevance_score"] == relevance.score


def test_radar_search_returns_query_analysis_and_ranked_matches():
    from internet_radar.search.radar_search import analyze_query, search_signals
    from internet_radar.storage.models import UserProfile

    profile = UserProfile(skills=["python"], interests=["browser agents"], goals=["learn"])
    signals = [
        SignalRecord(
            id="a",
            topic="browser agents",
            title="Browser agents exploding",
            source="GitHub Search",
            category="code",
            score=88,
            velocity=38,
            summary="Python automation agents.",
        ),
        SignalRecord(
            id="b",
            topic="agentic browser automation",
            title="Agentic browser automation papers increase",
            source="arXiv",
            category="research",
            score=77,
            velocity=27,
        ),
        SignalRecord(id="c", topic="frontend", title="CSS framework", source="Dev.to", category="news", score=65),
    ]

    results = search_signals(signals, "browser agents", profile=profile)
    analysis = analyze_query(signals, "browser agents", profile=profile)

    assert [result.signal.id for result in results] == ["a", "b"]
    assert results[0].match_score > results[1].match_score
    assert analysis["query"] == "browser agents"
    assert analysis["matching_signals"] == 2
    assert analysis["source_count"] == 2
    assert analysis["top_categories"] == ["code", "research"]
    assert analysis["personal_relevance"] >= 80


def test_radar_search_semantic_expansion_is_opt_in():
    from internet_radar.search.radar_search import search_signals
    from internet_radar.storage.models import SignalRecord

    signals = [
        SignalRecord(id="a", topic="browser agents", title="Browser agents exploding", source="GitHub Search", category="code", score=88),
        SignalRecord(id="b", topic="css", title="CSS framework", source="Dev.to", category="news", score=65),
    ]

    assert [result.signal.id for result in search_signals(signals, "browser agents")] == ["a"]
    assert len(search_signals(signals, "browser agents", include_semantic=True)) >= 1


def test_dashboard_payload_exposes_profile_and_search_context():
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.storage.models import UserProfile

    profile = UserProfile(
        skills=["python", "ai"],
        interests=["browser agents", "mcp"],
        goals=["find internships"],
        blocked_topics=[],
        alert_threshold=80,
    )
    signals = [
        SignalRecord(
            id="a",
            topic="browser agents",
            title="Browser agents exploding",
            source="GitHub Search",
            category="code",
            score=88,
            summary="Python AI automation.",
        )
    ]

    payload = build_dashboard_payload(signals, active_sources=3, llm_status="ollama:qwen2.5:0.5b", profile=profile)

    assert payload["briefing"]["personalized_signals"][0].id == "a"
    assert payload["profile"]["profile"]["skills"] == ["python", "ai"]
    assert payload["profile"]["profile"]["alert_threshold"] == 80
    assert payload["radar_search"]["suggested_queries"] == ["browser agents", "mcp"]
    assert payload["radar_search"]["query_analysis"]["browser agents"]["matching_signals"] == 1
