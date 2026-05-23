from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def test_sentiment_pipeline_scores_frustration_and_enriches_metadata():
    from internet_radar.signals.sentiment_pipeline import analyze_sentiment, enrich_signals_with_sentiment

    signal = SignalRecord(
        id="pain-1",
        topic="ai resume tools",
        title="I hate that AI resume builders are broken",
        source="Reddit JSON",
        category="social",
        score=72,
        summary="Too much manual editing, expensive subscriptions, and no export works.",
    )

    result = analyze_sentiment(signal)
    enriched = enrich_signals_with_sentiment([signal])

    assert result.label == "negative"
    assert result.frustration_score >= 80
    assert {"hate", "broken", "expensive", "manual"}.issubset(set(result.pain_terms))
    assert enriched[0].metadata["sentiment"] == "negative"
    assert enriched[0].metadata["frustration_score"] == result.frustration_score


def test_gap_finder_clusters_repeated_pain_into_startup_gap():
    from internet_radar.signals.gap_finder import find_startup_gaps

    signals = [
        SignalRecord(
            id="reddit-1",
            topic="ai resume tools",
            title="AI resume builder is broken",
            source="Reddit JSON",
            category="social",
            score=76,
            summary="I hate the manual editing and expensive subscription.",
        ),
        SignalRecord(
            id="app-1",
            topic="ai resume tools",
            title="Resume app needs too much manual editing",
            source="iTunes App Store",
            category="app_stores",
            score=70,
            summary="Broken export and expensive credits.",
            metadata={"rating": 2.1},
        ),
        SignalRecord(
            id="positive-1",
            topic="browser agents",
            title="Browser agents are useful",
            source="GitHub Search",
            category="code",
            score=88,
            summary="Developers love automation.",
        ),
    ]

    gaps = find_startup_gaps(signals, min_complaints=2)

    assert len(gaps) == 1
    assert gaps[0].problem == "ai resume tools"
    assert gaps[0].complaint_count == 2
    assert gaps[0].pain_level >= 8
    assert gaps[0].sources == ["Reddit JSON", "iTunes App Store"]
    assert "manual editing" in gaps[0].best_quote.lower()
    assert "ai resume tools" in gaps[0].startup_idea.lower()


def test_dashboard_payload_exposes_gap_and_sentiment_context():
    from internet_radar.dashboard_data import build_dashboard_payload

    signals = [
        SignalRecord(
            id="reddit-1",
            topic="ai resume tools",
            title="AI resume builder is broken",
            source="Reddit JSON",
            category="social",
            score=76,
            summary="I hate the manual editing and expensive subscription.",
        ),
        SignalRecord(
            id="app-1",
            topic="ai resume tools",
            title="Resume app needs too much manual editing",
            source="iTunes App Store",
            category="app_stores",
            score=70,
            summary="Broken export and expensive credits.",
            metadata={"rating": 2.1},
        ),
    ]

    payload = build_dashboard_payload(signals, active_sources=2)

    assert payload["startup_gaps"]["gap_clusters"][0].problem == "ai resume tools"
    assert payload["community_pulse"]["sentiment_summary"]["negative"] == 1
    assert payload["app_store_pain"]["pain_clusters"][0].problem == "ai resume tools"


def test_dashboard_frames_format_gap_clusters_and_sentiment_summary():
    from dashboard.app import _gaps_to_frame, _sentiment_to_frame
    from internet_radar.signals.gap_finder import GapCluster

    gap_frame = _gaps_to_frame(
        [
            GapCluster(
                problem="ai resume tools",
                complaint_count=2,
                pain_level=9,
                sources=["Reddit JSON", "iTunes App Store"],
                best_quote="Resume app needs too much manual editing.",
                startup_idea="Build a simpler AI resume editor.",
                score=82,
                signal_ids=["a", "b"],
            )
        ]
    )
    sentiment_frame = _sentiment_to_frame({"positive": 1, "neutral": 2, "negative": 3})

    assert gap_frame.iloc[0]["problem"] == "ai resume tools"
    assert gap_frame.iloc[0]["sources"] == "Reddit JSON, iTunes App Store"
    assert sentiment_frame.to_dict("records") == [
        {"sentiment": "positive", "signals": 1},
        {"sentiment": "neutral", "signals": 2},
        {"sentiment": "negative", "signals": 3},
    ]
