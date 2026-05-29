from __future__ import annotations

from internet_radar.storage.models import SignalRecord


def _signals() -> list[SignalRecord]:
    return [
        SignalRecord(id="code-1", topic="mcp", title="MCP repo", source="GitHub Search", category="code", score=90),
        SignalRecord(id="code-2", topic="agents", title="Agent package", source="PyPI", category="code", score=70),
        SignalRecord(id="job-1", topic="ai intern", title="AI internship", source="RemoteOK", category="jobs", score=80),
    ]


def test_signal_analytics_uses_duckdb_backend_for_dashboard_distributions():
    from internet_radar.storage.analytics import compute_signal_analytics

    analytics = compute_signal_analytics(_signals(), backend="duckdb")

    assert analytics.backend == "duckdb"
    assert analytics.category_distribution == [
        {"category": "code", "signals": 2, "avg_score": 80.0},
        {"category": "jobs", "signals": 1, "avg_score": 80.0},
    ]
    assert analytics.source_distribution[0] == {"source": "GitHub Search", "signals": 1, "score": 90.0}


def test_signal_analytics_python_backend_matches_duckdb_shape():
    from internet_radar.storage.analytics import compute_signal_analytics

    analytics = compute_signal_analytics(_signals(), backend="python")

    assert analytics.backend == "python"
    assert analytics.category_distribution == [
        {"category": "code", "signals": 2, "avg_score": 80.0},
        {"category": "jobs", "signals": 1, "avg_score": 80.0},
    ]
    assert {row["source"] for row in analytics.source_distribution} == {"GitHub Search", "PyPI", "RemoteOK"}
