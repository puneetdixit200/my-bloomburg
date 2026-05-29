from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from internet_radar.alerts.alert_manager import AlertMessage
from internet_radar.alerts.dispatcher import AlertDispatchResult, HttpPost
from internet_radar.storage.migrations import apply_migrations


@dataclass(frozen=True)
class AlertOutboxItem:
    id: int
    signal_id: str
    kind: str
    title: str
    body: str
    channel: str
    score: int
    status: str
    attempts: int
    last_error: str
    created_at: str
    updated_at: str


class AlertOutbox:
    def __init__(self, db_path: str | Path = "data/radar.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            apply_migrations(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def record_results(self, alert: AlertMessage, results: list[AlertDispatchResult]) -> int:
        inserted = 0
        for result in results:
            if result.sent:
                continue
            inserted += 1 if self.enqueue(alert, channel=result.channel, detail=result.detail) else 0
        return inserted

    def enqueue(self, alert: AlertMessage, *, channel: str, detail: str, coalesce: bool = True) -> int:
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            if coalesce:
                existing = conn.execute(
                    """
                    SELECT id
                    FROM alert_outbox
                    WHERE signal_id = ? AND channel = ? AND status = 'pending'
                    ORDER BY updated_at DESC, id DESC
                    LIMIT 1
                    """,
                    (alert.signal_id, channel),
                ).fetchone()
                if existing is not None:
                    conn.execute(
                        """
                        UPDATE alert_outbox
                        SET kind = ?,
                            title = ?,
                            body = ?,
                            score = ?,
                            attempts = attempts + 1,
                            last_error = ?,
                            updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            alert.kind,
                            alert.title,
                            alert.body,
                            int(alert.score),
                            detail,
                            now,
                            int(existing["id"]),
                        ),
                    )
                    return 0
            cursor = conn.execute(
                """
                INSERT INTO alert_outbox (
                    signal_id, kind, title, body, channel, score, status, attempts, last_error, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?, ?)
                """,
                (
                    alert.signal_id,
                    alert.kind,
                    alert.title,
                    alert.body,
                    channel,
                    int(alert.score),
                    detail,
                    now,
                    now,
                ),
            )
        return int(cursor.lastrowid)

    def compact_pending(self) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM alert_outbox
                WHERE status = 'pending'
                ORDER BY signal_id, channel, updated_at ASC, id ASC
                """
            ).fetchall()
            by_key: dict[tuple[str, str], list[sqlite3.Row]] = {}
            for row in rows:
                key = (str(row["signal_id"]), str(row["channel"]))
                by_key.setdefault(key, []).append(row)

            deleted = 0
            for group in by_key.values():
                if len(group) <= 1:
                    continue
                keep = group[-1]
                delete_ids = [int(row["id"]) for row in group[:-1]]
                attempts = sum(int(row["attempts"]) for row in group)
                created_at = min(str(row["created_at"]) for row in group)
                conn.execute(
                    """
                    UPDATE alert_outbox
                    SET attempts = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (attempts, created_at, int(keep["id"])),
                )
                conn.executemany("DELETE FROM alert_outbox WHERE id = ?", [(item_id,) for item_id in delete_ids])
                deleted += len(delete_ids)
        return deleted

    def list_pending(self, limit: int = 100) -> list[AlertOutboxItem]:
        return self._list(status="pending", limit=limit)

    def count_pending(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM alert_outbox WHERE status = 'pending'").fetchone()[0])

    def list_recent(self, limit: int = 100) -> list[AlertOutboxItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_outbox ORDER BY updated_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def retry_pending(
        self,
        *,
        config: dict[str, str] | None = None,
        http_post: HttpPost | None = None,
        limit: int = 25,
        respect_backoff: bool = True,
        now: datetime | None = None,
    ) -> list[AlertDispatchResult]:
        from internet_radar.alerts.dispatcher import alert_readiness, dispatch_alert

        results: list[AlertDispatchResult] = []
        self.compact_pending()
        ready_channels = {item.channel for item in alert_readiness(config or {}) if item.ready}
        scan_limit = max(limit * 10, limit)
        retry_now = now or datetime.now(UTC)
        for item in self.list_pending(limit=scan_limit):
            if len(results) >= limit:
                break
            if item.channel not in ready_channels:
                continue
            if respect_backoff and not _retry_due(item, retry_now):
                continue
            alert = AlertMessage(
                signal_id=item.signal_id,
                kind=item.kind,
                title=item.title,
                body=item.body,
                channels=[item.channel],
                score=item.score,
            )
            kwargs: dict[str, Any] = {"config": config or {}}
            if http_post is not None:
                kwargs["http_post"] = http_post
            retry_results = dispatch_alert(alert, **kwargs)
            result = retry_results[0] if retry_results else AlertDispatchResult(item.channel, False, "no result")
            self._mark_result(item.id, result)
            results.append(result)
        return results

    def send_pending_digest(
        self,
        *,
        channel: str,
        config: dict[str, str] | None = None,
        http_post: HttpPost | None = None,
        limit: int = 500,
    ) -> AlertDispatchResult:
        from internet_radar.alerts.dispatcher import dispatch_alert

        items = self._list_channel_pending(channel=channel, limit=limit)
        if not items:
            return AlertDispatchResult(channel=channel, sent=True, detail="no pending alerts")
        alert = AlertMessage(
            signal_id=f"alert-outbox-digest:{channel}",
            kind="ALERT_OUTBOX_DIGEST",
            title="Internet Radar alert backlog recovered",
            body=_digest_body(channel, items),
            channels=[channel],
            score=max(item.score for item in items),
        )
        kwargs: dict[str, Any] = {"config": config or {}}
        if http_post is not None:
            kwargs["http_post"] = http_post
        retry_results = dispatch_alert(alert, **kwargs)
        result = retry_results[0] if retry_results else AlertDispatchResult(channel, False, "no result")
        if result.sent:
            self._mark_digested([item.id for item in items], result.detail)
        else:
            self._mark_digest_failure([item.id for item in items], result.detail)
        return result

    def _list(self, *, status: str, limit: int) -> list[AlertOutboxItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alert_outbox WHERE status = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def _list_channel_pending(self, *, channel: str, limit: int) -> list[AlertOutboxItem]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM alert_outbox
                WHERE status = 'pending' AND channel = ?
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (channel, limit),
            ).fetchall()
        return [_row_to_item(row) for row in rows]

    def _mark_result(self, item_id: int, result: AlertDispatchResult) -> None:
        now = datetime.now(UTC).isoformat()
        status = "sent" if result.sent else "pending"
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE alert_outbox
                SET status = ?,
                    attempts = attempts + 1,
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, "" if result.sent else result.detail, now, item_id),
            )

    def _mark_digested(self, item_ids: list[int], detail: str) -> None:
        if not item_ids:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE alert_outbox
                SET status = 'digested',
                    last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [(f"digest sent: {detail}", now, item_id) for item_id in item_ids],
            )

    def _mark_digest_failure(self, item_ids: list[int], detail: str) -> None:
        if not item_ids:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.executemany(
                """
                UPDATE alert_outbox
                SET last_error = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                [(f"digest failed: {detail}", now, item_id) for item_id in item_ids],
            )


def _retry_due(item: AlertOutboxItem, now: datetime) -> bool:
    backoff = _retry_backoff(item.attempts)
    if backoff.total_seconds() <= 0:
        return True
    updated_at = _parse_timestamp(item.updated_at)
    if updated_at is None:
        return True
    return now - updated_at >= backoff


def _retry_backoff(attempts: int) -> timedelta:
    if attempts <= 1:
        return timedelta(seconds=0)
    return timedelta(seconds=min(3600, 60 * 2 ** (attempts - 1)))


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _digest_body(channel: str, items: list[AlertOutboxItem]) -> str:
    lines = [
        f"{len(items)} pending {channel} alerts were queued while delivery was down.",
        "Open the Internet Radar dashboard for the full backlog.",
        "",
        "Top queued alerts:",
    ]
    for item in sorted(items, key=lambda value: value.score, reverse=True)[:5]:
        lines.append(f"- {item.title} ({item.score}/100)")
    return "\n".join(lines)


def _row_to_item(row: sqlite3.Row) -> AlertOutboxItem:
    return AlertOutboxItem(
        id=int(row["id"]),
        signal_id=str(row["signal_id"]),
        kind=str(row["kind"]),
        title=str(row["title"]),
        body=str(row["body"]),
        channel=str(row["channel"]),
        score=int(row["score"]),
        status=str(row["status"]),
        attempts=int(row["attempts"]),
        last_error=str(row["last_error"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )
