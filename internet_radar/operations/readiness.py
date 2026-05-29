from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from internet_radar.alerts.dispatcher import alert_readiness
from internet_radar.scheduler.heartbeat import latest_scheduler_heartbeat
from internet_radar.scheduler.jobs import build_job_plan
from internet_radar.storage.analytics import compute_signal_analytics
from internet_radar.storage.models import BriefingPayload


@dataclass(frozen=True)
class ReadinessCheck:
    key: str
    area: str
    status: str
    detail: str
    next_action: str


@dataclass(frozen=True)
class MakeRealReadinessReport:
    checks: list[ReadinessCheck]

    @property
    def ready_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "ready")

    @property
    def blocker_count(self) -> int:
        return sum(1 for check in self.checks if check.status == "blocked")

    @property
    def blockers(self) -> list[str]:
        return [check.key for check in self.checks if check.status == "blocked"]


def build_make_real_readiness(
    *,
    db_path: str | Path | None = None,
    payload: BriefingPayload | None = None,
    external_checks: Mapping[str, Mapping[str, Any]] | None = None,
) -> MakeRealReadinessReport:
    db_path = Path(db_path or os.getenv("INTERNET_RADAR_DB", "data/radar.sqlite"))
    external_checks = external_checks or {}
    checks = [
        _time_series_check(db_path),
        _scheduler_check(db_path),
        _live_collection_check(payload),
        _reddit_json_check(payload),
        _reddit_oauth_check(external_checks.get("reddit_oauth")),
        _alert_dispatch_check(db_path),
        _telegram_check(external_checks.get("telegram")),
        _llm_pipeline_check(payload),
        _semantic_vectors_check(),
        _duckdb_check(payload),
        _daily_runtime_check(payload),
    ]
    return MakeRealReadinessReport(checks=checks)


def readiness_frame(report: MakeRealReadinessReport) -> pd.DataFrame:
    return pd.DataFrame([check.__dict__ for check in report.checks])


def _time_series_check(db_path: Path) -> ReadinessCheck:
    count = _sqlite_count(db_path, "signal_snapshots")
    if count > 0:
        return _ready("time_series", "Trend detection", f"{count} signal snapshots stored.")
    return _blocked("time_series", "Trend detection", "No signal_snapshots rows found.", "Run a live collection to build history.")


def _scheduler_check(db_path: Path) -> ReadinessCheck:
    jobs = build_job_plan().jobs
    has_retry = any(job.name == "alert_outbox_retry" for job in jobs)
    if len(jobs) < 32 or not has_retry:
        return _blocked("scheduler", "Auto collection", f"{len(jobs)} jobs configured.", "Register all cadence and retry jobs.")
    heartbeat = latest_scheduler_heartbeat(db_path)
    if heartbeat is None:
        return _blocked("scheduler", "Auto collection", "No scheduler heartbeat found.", "Start the scheduler or run python scheduler/runner.py --once.")
    if heartbeat.status != "ok":
        return _blocked(
            "scheduler",
            "Auto collection",
            f"Latest heartbeat for {heartbeat.job_name} failed: {heartbeat.detail}",
            "Inspect scheduler logs and rerun the failed job.",
        )
    heartbeat_at = _parse_timestamp(heartbeat.recorded_at)
    if heartbeat_at is None:
        return _blocked(
            "scheduler",
            "Auto collection",
            f"Latest heartbeat for {heartbeat.job_name} has an invalid timestamp: {heartbeat.recorded_at}",
            "Restart the scheduler so it records a fresh heartbeat.",
        )
    max_age = _scheduler_heartbeat_max_age()
    age = datetime.now(UTC) - heartbeat_at
    if age > max_age:
        return _blocked(
            "scheduler",
            "Auto collection",
            f"Latest heartbeat for {heartbeat.job_name} is stale: {heartbeat.recorded_at}.",
            "Restart the scheduler so it records a fresh daemon heartbeat.",
        )
    return _ready(
        "scheduler",
        "Auto collection",
        f"{len(jobs)} jobs configured; latest heartbeat {heartbeat.job_name} at {heartbeat.recorded_at} signals={heartbeat.signals_24h} sources={heartbeat.active_sources}.",
    )


def _live_collection_check(payload: BriefingPayload | None) -> ReadinessCheck:
    if payload and payload.collection_mode == "live" and payload.active_sources >= 50 and payload.signals_24h >= 100:
        return _ready("live_collection", "Live data", f"{payload.active_sources} active sources and {payload.signals_24h} dashboard signals.")
    if payload:
        return _blocked("live_collection", "Live data", f"Mode={payload.collection_mode}, sources={payload.active_sources}, signals={payload.signals_24h}.", "Run a live collection.")
    return _blocked("live_collection", "Live data", "No latest payload was provided.", "Run a live collection.")


def _reddit_json_check(payload: BriefingPayload | None) -> ReadinessCheck:
    health = (payload.source_health or {}).get("Reddit JSON", "") if payload else ""
    if health.startswith(("live", "database")):
        return _ready("reddit_json", "Reddit no-key scan", health)
    return _blocked("reddit_json", "Reddit no-key scan", health or "No Reddit JSON health in latest payload.", "Run live collection or check public Reddit JSON access.")


def _reddit_oauth_check(external_check: Mapping[str, Any] | None = None) -> ReadinessCheck:
    if external_check is not None:
        detail = str(external_check.get("detail") or "Reddit OAuth verification failed.")
        if external_check.get("valid"):
            return _ready("reddit_oauth", "Reddit OAuth", detail)
        if external_check.get("configured"):
            return _blocked("reddit_oauth", "Reddit OAuth", detail, "Fix the Reddit script app client id/secret.")
        return _blocked("reddit_oauth", "Reddit OAuth", detail, "Add the Reddit script app credentials.")
    if os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"):
        return _ready("reddit_oauth", "Reddit OAuth", "Credentials are configured.")
    return _blocked("reddit_oauth", "Reddit OAuth", "REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET missing.", "Add the Reddit script app credentials.")


def _alert_dispatch_check(db_path: Path) -> ReadinessCheck:
    dispatch_enabled = os.getenv("INTERNET_RADAR_DISPATCH_ALERTS", "0") == "1"
    ready_channels = [item.channel for item in alert_readiness() if item.ready]
    pending_failure = _latest_pending_alert_failure(db_path, channels=ready_channels)
    if pending_failure is not None:
        pending_count, channel, error = pending_failure
        return _blocked(
            "alert_dispatch",
            "Alerts",
            f"{pending_count} pending alert failures; latest {channel}: {error}",
            "Fix alert delivery and let the outbox retry job mark failures sent.",
        )
    if dispatch_enabled and ready_channels:
        return _ready("alert_dispatch", "Alerts", f"Dispatch enabled; ready channels: {', '.join(ready_channels)}.")
    return _blocked("alert_dispatch", "Alerts", "No ready dispatch channel or dispatch disabled.", "Set dispatch on and configure at least one channel.")


def _telegram_check(external_check: Mapping[str, Any] | None = None) -> ReadinessCheck:
    if external_check is not None:
        detail = str(external_check.get("detail") or "Telegram credential verification failed.")
        if external_check.get("valid"):
            return _ready("telegram", "Telegram", detail)
        if external_check.get("configured"):
            return _blocked("telegram", "Telegram", detail, "Fix the Telegram bot token or chat id.")
        return _blocked("telegram", "Telegram", detail, "Create the bot and add chat credentials.")
    if os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"):
        return _ready("telegram", "Telegram", "Telegram bot token and chat id are configured.")
    return _blocked("telegram", "Telegram", "TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.", "Create the bot and add chat credentials.")


def _llm_pipeline_check(payload: BriefingPayload | None) -> ReadinessCheck:
    insight = (payload.analysis_artifacts or {}).get("llm_generated_insight", {}) if payload else {}
    if insight.get("status") == "generated":
        provider = insight.get("provider", "unknown")
        model = insight.get("model", "unknown")
        return _ready("llm_pipeline", "AI analysis", f"Generated insight via {provider}:{model}.")
    if payload and payload.llm_status and not payload.llm_status.startswith("deterministic"):
        return _ready("llm_pipeline", "AI analysis", f"Pipeline route is {payload.llm_status}.")
    return _blocked("llm_pipeline", "AI analysis", "No generated LLM insight in latest payload.", "Enable LLM analysis and run collection.")


def _semantic_vectors_check() -> ReadinessCheck:
    backend = os.getenv("INTERNET_RADAR_VECTOR_BACKEND", "auto").strip().lower()
    if backend == "gemini" and os.getenv("GEMINI_API_KEY"):
        return _ready("semantic_vectors", "Semantic search", "Gemini embedding backend configured.")
    if backend in {"auto", "deterministic", "chroma"}:
        return _ready("semantic_vectors", "Semantic search", f"Vector backend configured as {backend}.")
    return _blocked("semantic_vectors", "Semantic search", f"Vector backend={backend}.", "Configure a supported vector backend.")


def _duckdb_check(payload: BriefingPayload | None) -> ReadinessCheck:
    if payload:
        analytics = compute_signal_analytics(payload.top_signals)
        if analytics.backend == "duckdb":
            return _ready("duckdb", "Analytics", "Dashboard distributions are using DuckDB.")
        return _ready("duckdb", "Analytics", f"DuckDB unavailable; using {analytics.backend} fallback.")
    return _blocked("duckdb", "Analytics", "No payload available to verify analytics backend.", "Load latest payload.")


def _daily_runtime_check(payload: BriefingPayload | None) -> ReadinessCheck:
    if payload and payload.loaded_from_cache:
        return _ready("daily_runtime", "Daily use", "Dashboard has a cached live payload.")
    if payload:
        return _ready("daily_runtime", "Daily use", "Dashboard payload can be built.")
    return _blocked("daily_runtime", "Daily use", "No payload available.", "Run dashboard or live collection.")


def _sqlite_count(db_path: Path, table: str) -> int:
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return 0


def _latest_pending_alert_failure(db_path: Path, *, channels: list[str] | None = None) -> tuple[int, str, str] | None:
    if not db_path.exists():
        return None
    channels = channels or []
    if not channels:
        return None
    placeholders = ",".join("?" for _ in channels)
    try:
        with sqlite3.connect(db_path) as conn:
            pending_count = int(
                conn.execute(
                    f"SELECT COUNT(*) FROM alert_outbox WHERE status = 'pending' AND channel IN ({placeholders})",
                    channels,
                ).fetchone()[0]
            )
            if pending_count == 0:
                return None
            row = conn.execute(
                f"""
                SELECT channel, last_error
                FROM alert_outbox
                WHERE status = 'pending' AND channel IN ({placeholders})
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                channels,
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return pending_count, str(row[0]), str(row[1])


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _scheduler_heartbeat_max_age() -> timedelta:
    try:
        minutes = int(os.getenv("INTERNET_RADAR_SCHEDULER_HEARTBEAT_MAX_AGE_MINUTES", "30"))
    except ValueError:
        minutes = 30
    return timedelta(minutes=max(1, minutes))


def _ready(key: str, area: str, detail: str) -> ReadinessCheck:
    return ReadinessCheck(key=key, area=area, status="ready", detail=detail, next_action="")


def _blocked(key: str, area: str, detail: str, next_action: str) -> ReadinessCheck:
    return ReadinessCheck(key=key, area=area, status="blocked", detail=detail, next_action=next_action)
