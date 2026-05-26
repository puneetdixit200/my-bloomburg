from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from internet_radar.storage.models import SignalRecord, SignalSnapshot
from internet_radar.storage.migrations import applied_versions, apply_migrations
from internet_radar.storage.supabase_store import SupabaseRadarStore


class RadarStore:
    def __init__(self, db_path: str | Path = "data/radar.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            apply_migrations(conn)

    def schema_versions(self) -> list[str]:
        with self._connect() as conn:
            return applied_versions(conn)

    def upsert_signals(self, signals: list[SignalRecord]) -> None:
        if not signals:
            return
        rows = []
        for signal in signals:
            row = signal.as_row()
            row["metadata"] = json.dumps(row["metadata"], sort_keys=True)
            rows.append(row)

        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signals (
                    id, topic, title, source, category, url, score, velocity, summary, observed_at, metadata
                )
                VALUES (
                    :id, :topic, :title, :source, :category, :url, :score, :velocity, :summary, :observed_at, :metadata
                )
                ON CONFLICT(id) DO UPDATE SET
                    topic=excluded.topic,
                    title=excluded.title,
                    source=excluded.source,
                    category=excluded.category,
                    url=excluded.url,
                    score=excluded.score,
                    velocity=excluded.velocity,
                    summary=excluded.summary,
                    observed_at=excluded.observed_at,
                    metadata=excluded.metadata
                """,
                rows,
            )

    def list_signals(self, category: str | None = None, limit: int = 100) -> list[SignalRecord]:
        sql = "SELECT * FROM signals"
        params: list[object] = []
        if category:
            sql += " WHERE category = ?"
            params.append(category)
        sql += " ORDER BY score DESC, observed_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return [self._row_to_signal(row) for row in rows]

    def record_signal_snapshots(
        self,
        signals: list[SignalRecord],
        *,
        run_id: str | None = None,
        observed_at: datetime | None = None,
    ) -> int:
        if not signals:
            return 0
        run_id = run_id or f"run-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        rows = []
        for signal in signals:
            signal_observed_at = observed_at or signal.observed_at
            for metric, value in _snapshot_metrics(signal).items():
                rows.append(
                    {
                        "run_id": run_id,
                        "signal_id": str(signal.id),
                        "topic": signal.topic,
                        "title": signal.title,
                        "source": signal.source,
                        "category": signal.category,
                        "metric": metric,
                        "value": float(value),
                        "observed_at": signal_observed_at.isoformat(),
                        "metadata": json.dumps(
                            {
                                "url": signal.url,
                                "score": signal.score,
                            },
                            sort_keys=True,
                        ),
                    }
                )
        if not rows:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO signal_snapshots (
                    run_id, signal_id, topic, title, source, category, metric, value, observed_at, metadata
                )
                VALUES (
                    :run_id, :signal_id, :topic, :title, :source, :category, :metric, :value, :observed_at, :metadata
                )
                """,
                rows,
            )
        return len(rows)

    def metric_history(
        self,
        *,
        signal_id: str | None = None,
        topic: str | None = None,
        metric: str,
        since: datetime | None = None,
        limit: int = 1000,
    ) -> list[SignalSnapshot]:
        sql = "SELECT * FROM signal_snapshots WHERE metric = ?"
        params: list[object] = [metric]
        if signal_id:
            sql += " AND signal_id = ?"
            params.append(signal_id)
        if topic:
            sql += " AND topic = ?"
            params.append(topic)
        if since:
            sql += " AND observed_at >= ?"
            params.append(since.isoformat())
        sql += " ORDER BY observed_at DESC, id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_snapshot(row) for row in rows]

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> SignalRecord:
        data = dict(row)
        data["metadata"] = json.loads(data.get("metadata") or "{}")
        return SignalRecord(**data)

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> SignalSnapshot:
        data = dict(row)
        data["metadata"] = json.loads(data.get("metadata") or "{}")
        return SignalSnapshot(**data)


def _snapshot_metrics(signal: SignalRecord) -> dict[str, float]:
    metrics = {
        "score": float(signal.score),
        "velocity": float(signal.velocity),
    }
    for key, value in signal.metadata.items():
        if key in metrics or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            metrics[str(key)] = float(value)
    return metrics


def create_store(db_path: str | Path | None = None) -> RadarStore | SupabaseRadarStore:
    backend = os.getenv("INTERNET_RADAR_STORAGE_BACKEND", "sqlite").strip().lower()
    if backend == "supabase":
        return SupabaseRadarStore()
    return RadarStore(db_path or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite"))
