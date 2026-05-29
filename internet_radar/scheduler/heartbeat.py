from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from internet_radar.storage.migrations import apply_migrations


@dataclass(frozen=True)
class SchedulerHeartbeat:
    job_name: str
    status: str
    signals_24h: int
    active_sources: int
    detail: str
    recorded_at: str


def record_scheduler_heartbeat(
    db_path: str | Path | None = None,
    *,
    job_name: str,
    status: str,
    signals_24h: int = 0,
    active_sources: int = 0,
    detail: str = "",
    recorded_at: datetime | None = None,
) -> None:
    path = _heartbeat_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = (recorded_at or datetime.now(UTC)).isoformat()
    with sqlite3.connect(path) as conn:
        apply_migrations(conn)
        conn.execute(
            """
            INSERT INTO scheduler_heartbeats (
                job_name, status, signals_24h, active_sources, detail, recorded_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_name,
                status,
                int(signals_24h),
                int(active_sources),
                detail[:500],
                timestamp,
            ),
        )


def latest_scheduler_heartbeat(db_path: str | Path | None = None) -> SchedulerHeartbeat | None:
    path = _heartbeat_db_path(db_path)
    if not path.exists():
        return None
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            apply_migrations(conn)
            row = conn.execute(
                """
                SELECT job_name, status, signals_24h, active_sources, detail, recorded_at
                FROM scheduler_heartbeats
                ORDER BY recorded_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return SchedulerHeartbeat(
        job_name=str(row["job_name"]),
        status=str(row["status"]),
        signals_24h=int(row["signals_24h"]),
        active_sources=int(row["active_sources"]),
        detail=str(row["detail"]),
        recorded_at=str(row["recorded_at"]),
    )


def _heartbeat_db_path(db_path: str | Path | None = None) -> Path:
    return Path(db_path or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite"))
