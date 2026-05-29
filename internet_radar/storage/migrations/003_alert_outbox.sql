CREATE TABLE IF NOT EXISTS alert_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT NOT NULL,
    score INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_alert_outbox_status_updated
ON alert_outbox(status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_alert_outbox_signal_channel
ON alert_outbox(signal_id, channel, status);
