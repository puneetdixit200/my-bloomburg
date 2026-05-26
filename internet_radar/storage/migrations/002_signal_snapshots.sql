CREATE TABLE IF NOT EXISTS signal_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    observed_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_signal_snapshots_signal_metric_time
ON signal_snapshots(signal_id, metric, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_snapshots_topic_metric_time
ON signal_snapshots(topic, metric, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_signal_snapshots_run
ON signal_snapshots(run_id);
