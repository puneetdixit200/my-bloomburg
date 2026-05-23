from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path


MIGRATIONS_DIR = Path(__file__).parent


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))


def apply_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """
    )
    applied = set(applied_versions(conn))
    for path in migration_files():
        version = path.stem
        if version in applied:
            continue
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (version, datetime.now(UTC).isoformat()),
        )
        applied.add(version)


def applied_versions(conn: sqlite3.Connection) -> list[str]:
    try:
        rows = conn.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows]
