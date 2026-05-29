CREATE TABLE IF NOT EXISTS scheduler_heartbeats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    signals_24h INTEGER NOT NULL DEFAULT 0,
    active_sources INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT '',
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scheduler_heartbeats_recorded_at
ON scheduler_heartbeats(recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_scheduler_heartbeats_job_recorded_at
ON scheduler_heartbeats(job_name, recorded_at DESC);
