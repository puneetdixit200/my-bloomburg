from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from internet_radar.storage.models import SignalRecord
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

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> SignalRecord:
        data = dict(row)
        data["metadata"] = json.loads(data.get("metadata") or "{}")
        return SignalRecord(**data)


def create_store(db_path: str | Path | None = None) -> RadarStore | SupabaseRadarStore:
    backend = os.getenv("INTERNET_RADAR_STORAGE_BACKEND", "sqlite").strip().lower()
    if backend == "supabase":
        return SupabaseRadarStore()
    return RadarStore(db_path or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite"))
