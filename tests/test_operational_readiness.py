from __future__ import annotations

from datetime import UTC, datetime

from internet_radar.storage.models import BriefingPayload, SignalRecord


def test_make_real_readiness_separates_ready_capabilities_from_external_blockers(tmp_path, monkeypatch):
    from internet_radar.storage.db import RadarStore
    from internet_radar.operations.readiness import build_make_real_readiness
    from internet_radar.scheduler.heartbeat import record_scheduler_heartbeat

    db_path = tmp_path / "radar.sqlite"
    store = RadarStore(db_path)
    observed_at = datetime.now(UTC)
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=92,
        metadata={"stars": 1200},
        observed_at=observed_at,
    )
    store.upsert_signals([signal])
    store.record_signal_snapshots([signal], observed_at=signal.observed_at)
    record_scheduler_heartbeat(
        db_path,
        job_name="github_trending_check",
        status="ok",
        signals_24h=500,
        active_sources=67,
        detail="scheduled run completed",
        recorded_at=signal.observed_at,
    )
    payload = BriefingPayload(
        active_sources=67,
        signals_24h=500,
        top_signals=[signal],
        source_health={"Reddit JSON": "live (40)"},
        analysis_artifacts={"llm_generated_insight": {"status": "generated"}},
        llm_status="ollama:qwen2.5:0.5b",
        collection_mode="live",
    )
    monkeypatch.setenv("INTERNET_RADAR_DISPATCH_ALERTS", "1")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("INTERNET_RADAR_VECTOR_BACKEND", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    report = build_make_real_readiness(db_path=db_path, payload=payload)
    by_key = {check.key: check for check in report.checks}

    assert report.ready_count >= 6
    assert by_key["time_series"].status == "ready"
    assert by_key["scheduler"].status == "ready"
    assert by_key["live_collection"].status == "ready"
    assert by_key["llm_pipeline"].status == "ready"
    assert by_key["semantic_vectors"].status == "ready"
    assert by_key["reddit_oauth"].status == "blocked"
    assert by_key["telegram"].status == "blocked"
    assert by_key["reddit_json"].status == "ready"
    assert set(report.blockers) == {"reddit_oauth", "telegram"}


def test_make_real_readiness_frame_is_dashboard_friendly(tmp_path):
    from internet_radar.operations.readiness import build_make_real_readiness, readiness_frame

    report = build_make_real_readiness(db_path=tmp_path / "missing.sqlite", payload=None)
    frame = readiness_frame(report)

    assert {"status", "area", "detail", "next_action"} <= set(frame.columns)
    assert "time_series" in set(frame["key"])


def test_make_real_readiness_uses_scheduler_heartbeat_as_runtime_evidence(tmp_path):
    from internet_radar.operations.readiness import build_make_real_readiness
    from internet_radar.scheduler.heartbeat import record_scheduler_heartbeat

    db_path = tmp_path / "radar.sqlite"

    report = build_make_real_readiness(db_path=db_path, payload=None)
    by_key = {check.key: check for check in report.checks}

    assert by_key["scheduler"].status == "blocked"
    assert "No scheduler heartbeat" in by_key["scheduler"].detail

    record_scheduler_heartbeat(
        db_path,
        job_name="daily_briefing_generate",
        status="ok",
        signals_24h=120,
        active_sources=18,
        detail="scheduled run completed",
    )

    report = build_make_real_readiness(db_path=db_path, payload=None)
    by_key = {check.key: check for check in report.checks}

    assert by_key["scheduler"].status == "ready"
    assert "daily_briefing_generate" in by_key["scheduler"].detail
    assert "signals=120" in by_key["scheduler"].detail


def test_make_real_readiness_blocks_stale_scheduler_heartbeat(tmp_path):
    from internet_radar.operations.readiness import build_make_real_readiness
    from internet_radar.scheduler.heartbeat import record_scheduler_heartbeat

    db_path = tmp_path / "radar.sqlite"
    record_scheduler_heartbeat(
        db_path,
        job_name="scheduler_daemon",
        status="ok",
        active_sources=32,
        detail="scheduler started",
        recorded_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    report = build_make_real_readiness(db_path=db_path, payload=None)
    by_key = {check.key: check for check in report.checks}

    assert by_key["scheduler"].status == "blocked"
    assert "stale" in by_key["scheduler"].detail


def test_make_real_readiness_blocks_alerts_when_outbox_has_pending_failures(monkeypatch, tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.operations.readiness import build_make_real_readiness

    db_path = tmp_path / "radar.sqlite"
    monkeypatch.setenv("INTERNET_RADAR_DISPATCH_ALERTS", "1")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")

    AlertOutbox(db_path).record_results(
        AlertMessage(
            signal_id="test-alert",
            kind="TEST_ALERT",
            title="Test alert",
            body="Alert delivery test",
            channels=["ntfy"],
            score=100,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: ConnectTimeout")],
    )
    AlertOutbox(db_path).record_results(
        AlertMessage(
            signal_id="test-alert-2",
            kind="TEST_ALERT",
            title="Test alert 2",
            body="Alert delivery test",
            channels=["telegram"],
            score=100,
        ),
        [AlertDispatchResult(channel="telegram", sent=False, detail="missing telegram credentials")],
    )

    report = build_make_real_readiness(db_path=db_path, payload=None)
    by_key = {check.key: check for check in report.checks}

    assert by_key["alert_dispatch"].status == "blocked"
    assert "1 pending alert failures" in by_key["alert_dispatch"].detail
    assert "ConnectTimeout" in by_key["alert_dispatch"].detail
    assert by_key["telegram"].status == "blocked"


def test_make_real_readiness_does_not_double_count_pending_unready_channel(monkeypatch, tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.operations.readiness import build_make_real_readiness

    db_path = tmp_path / "radar.sqlite"
    monkeypatch.setenv("INTERNET_RADAR_DISPATCH_ALERTS", "1")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    AlertOutbox(db_path).record_results(
        AlertMessage(
            signal_id="test-alert",
            kind="TEST_ALERT",
            title="Test alert",
            body="Alert delivery test",
            channels=["telegram"],
            score=100,
        ),
        [AlertDispatchResult(channel="telegram", sent=False, detail="missing telegram credentials")],
    )

    report = build_make_real_readiness(db_path=db_path, payload=None)
    by_key = {check.key: check for check in report.checks}

    assert by_key["alert_dispatch"].status == "ready"
    assert by_key["telegram"].status == "blocked"


def test_make_real_readiness_can_use_external_credential_verification(monkeypatch, tmp_path):
    from internet_radar.operations.readiness import build_make_real_readiness

    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    report = build_make_real_readiness(
        db_path=tmp_path / "missing.sqlite",
        payload=None,
        external_checks={
            "reddit_oauth": {
                "configured": True,
                "valid": False,
                "detail": "401 invalid_client",
            },
            "telegram": {
                "configured": True,
                "valid": True,
                "detail": "chat resolved",
                "chat": {"chat_id": "12345", "type": "private"},
            },
        },
    )
    by_key = {check.key: check for check in report.checks}

    assert by_key["reddit_oauth"].status == "blocked"
    assert by_key["reddit_oauth"].detail == "401 invalid_client"
    assert by_key["telegram"].status == "ready"
    assert by_key["telegram"].detail == "chat resolved"
