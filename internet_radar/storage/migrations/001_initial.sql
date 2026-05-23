CREATE TABLE IF NOT EXISTS signals (
    id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    url TEXT NOT NULL,
    score INTEGER NOT NULL,
    velocity REAL NOT NULL,
    summary TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    metadata TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_category ON signals(category);
CREATE INDEX IF NOT EXISTS idx_signals_score ON signals(score DESC);
