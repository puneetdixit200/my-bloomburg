from __future__ import annotations

import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Literal

import pandas as pd

from internet_radar.storage.models import SignalRecord


AnalyticsBackend = Literal["auto", "duckdb", "python"]


@dataclass(frozen=True)
class SignalAnalytics:
    backend: str
    category_distribution: list[dict[str, object]]
    source_distribution: list[dict[str, object]]


def compute_signal_analytics(
    signals: list[SignalRecord],
    *,
    backend: AnalyticsBackend | None = None,
) -> SignalAnalytics:
    rows = [
        {
            "category": signal.category,
            "source": signal.source,
            "score": float(signal.score),
        }
        for signal in signals
    ]
    requested = (backend or os.getenv("INTERNET_RADAR_ANALYTICS_BACKEND", "auto")).strip().lower()
    if requested not in {"auto", "duckdb", "python"}:
        requested = "auto"
    if requested in {"auto", "duckdb"}:
        try:
            return _duckdb_analytics(rows)
        except Exception:
            if requested == "duckdb":
                return _python_analytics(rows, backend_name="python-fallback")
    return _python_analytics(rows)


def _duckdb_analytics(rows: list[dict[str, object]]) -> SignalAnalytics:
    import duckdb

    if not rows:
        return SignalAnalytics(backend="duckdb", category_distribution=[], source_distribution=[])
    frame = pd.DataFrame(rows)
    with duckdb.connect(":memory:") as conn:
        conn.register("signals", frame)
        category_distribution = [
            {"category": str(category), "signals": int(signals), "avg_score": round(float(avg_score), 3)}
            for category, signals, avg_score in conn.execute(
                """
                SELECT category, COUNT(*) AS signals, AVG(score) AS avg_score
                FROM signals
                GROUP BY category
                ORDER BY signals DESC, category ASC
                """
            ).fetchall()
        ]
        source_distribution = [
            {"source": str(source), "signals": int(signals), "score": round(float(score), 3)}
            for source, signals, score in conn.execute(
                """
                SELECT source, COUNT(*) AS signals, AVG(score) AS score
                FROM signals
                GROUP BY source
                ORDER BY score DESC, source ASC
                LIMIT 12
                """
            ).fetchall()
        ]
    return SignalAnalytics(
        backend="duckdb",
        category_distribution=category_distribution,
        source_distribution=source_distribution,
    )


def _python_analytics(rows: list[dict[str, object]], *, backend_name: str = "python") -> SignalAnalytics:
    category_scores: dict[str, list[float]] = defaultdict(list)
    source_scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        score = float(row["score"])
        category_scores[str(row["category"])].append(score)
        source_scores[str(row["source"])].append(score)

    category_distribution = [
        {"category": category, "signals": len(scores), "avg_score": round(sum(scores) / len(scores), 3)}
        for category, scores in category_scores.items()
    ]
    category_distribution.sort(key=lambda row: (-int(row["signals"]), str(row["category"])))

    source_distribution = [
        {"source": source, "signals": len(scores), "score": round(sum(scores) / len(scores), 3)}
        for source, scores in source_scores.items()
    ]
    source_distribution.sort(key=lambda row: (-float(row["score"]), str(row["source"])))
    return SignalAnalytics(
        backend=backend_name,
        category_distribution=category_distribution,
        source_distribution=source_distribution[:12],
    )
