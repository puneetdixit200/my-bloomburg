from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_cross_source_multiplier_matches_architecture_thresholds():
    from internet_radar.signals.cross_source_multiplier import apply_cross_source_multiplier, cross_source_multiplier

    assert cross_source_multiplier(1) == 1.0
    assert cross_source_multiplier(2) == 1.0
    assert cross_source_multiplier(3) == 1.15
    assert cross_source_multiplier(5) == 1.3
    assert apply_cross_source_multiplier(80, 3) == 92
    assert apply_cross_source_multiplier(90, 5) == 100


def test_build_source_agreements_groups_topics_into_matrix_rows():
    from internet_radar.signals.cross_source_multiplier import build_source_agreements

    signals = [
        SignalRecord(id="gh", topic="browser agents", title="Browser agent repo", source="GitHub", category="code", score=84),
        SignalRecord(id="hn", topic="Browser Agents", title="HN browser agent", source="Hacker News", category="social", score=88),
        SignalRecord(id="job", topic="browser agents", title="Browser agent jobs", source="RemoteOK", category="jobs", score=76),
        SignalRecord(id="paper", topic="browser agents", title="Browser agent paper", source="arXiv", category="research", score=80),
        SignalRecord(id="solo", topic="css grid", title="CSS grid", source="Dev.to", category="news", score=60),
    ]

    agreements = build_source_agreements(signals, known_source_count=8)

    assert agreements[0].topic == "browser agents"
    assert agreements[0].source_count == 4
    assert agreements[0].sources == ["GitHub", "Hacker News", "RemoteOK", "arXiv"]
    assert agreements[0].multiplier == 1.15
    assert agreements[0].score == 100
    assert agreements[0].verdict == "STRONG"
    assert agreements[1].verdict == "SINGLE SOURCE - WATCH"


def test_dashboard_payload_exposes_source_agreements_for_trend_velocity():
    from internet_radar.dashboard_data import build_dashboard_payload

    signals = [
        SignalRecord(id="gh", topic="local llm", title="Local LLM repo", source="GitHub", category="code", score=85),
        SignalRecord(id="hn", topic="local llm", title="Local LLM HN", source="Hacker News", category="social", score=82),
        SignalRecord(id="arxiv", topic="local llm", title="Local LLM paper", source="arXiv", category="research", score=79),
    ]

    payload = build_dashboard_payload(signals)

    assert payload["trend_velocity"]["source_agreements"][0].topic == "local llm"
    assert payload["trend_velocity"]["source_agreements"][0].verdict == "STRONG"
