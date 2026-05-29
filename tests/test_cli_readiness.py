from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import UTC, datetime

from internet_radar.storage.models import BriefingPayload, SignalRecord


def test_cli_readiness_uses_cached_payload_and_reports_external_blockers(tmp_path, monkeypatch, capsys):
    from internet_radar.cli import main
    from internet_radar.scheduler.heartbeat import record_scheduler_heartbeat
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.payload_cache import save_briefing_payload

    db_path = tmp_path / "radar.sqlite"
    cache_path = tmp_path / "latest_payload.json"
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=92,
        metadata={"stars": 1200},
    )
    store = RadarStore(db_path)
    store.upsert_signals([signal])
    store.record_signal_snapshots([signal])
    record_scheduler_heartbeat(
        db_path,
        job_name="github_trending_check",
        status="ok",
        signals_24h=500,
        active_sources=67,
        detail="scheduled run completed",
    )
    save_briefing_payload(
        BriefingPayload(
            active_sources=67,
            signals_24h=500,
            top_signals=[signal],
            source_health={"Reddit JSON": "live (40)"},
            analysis_artifacts={"llm_generated_insight": {"status": "generated", "provider": "ollama", "model": "qwen2.5:0.5b"}},
            llm_status="ollama:qwen2.5:0.5b",
            collection_mode="live",
        ),
        cache_path,
    )
    monkeypatch.setenv("INTERNET_RADAR_PAYLOAD_CACHE", str(cache_path))
    monkeypatch.setenv("INTERNET_RADAR_DISPATCH_ALERTS", "1")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("INTERNET_RADAR_VECTOR_BACKEND", "gemini")
    monkeypatch.setenv("INTERNET_RADAR_DISABLE_DOTENV", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["internet-radar-run", "--readiness", "--db", str(db_path)])

    main()

    output = json.loads(capsys.readouterr().out)

    assert output["ready_count"] >= 9
    assert output["blocker_count"] == 2
    assert output["blockers"] == ["reddit_oauth", "telegram"]
    statuses = {check["key"]: check["status"] for check in output["checks"]}
    assert statuses["live_collection"] == "ready"
    assert statuses["reddit_json"] == "ready"
    assert statuses["llm_pipeline"] == "ready"


def test_cli_readiness_loads_local_env_file_for_direct_terminal_use(tmp_path, monkeypatch, capsys):
    from internet_radar.cli import main
    from internet_radar.scheduler.heartbeat import record_scheduler_heartbeat
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.payload_cache import save_briefing_payload

    db_path = tmp_path / "radar.sqlite"
    cache_path = tmp_path / "latest_payload.json"
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=92,
        metadata={"stars": 1200},
    )
    RadarStore(db_path).record_signal_snapshots([signal])
    record_scheduler_heartbeat(
        db_path,
        job_name="github_trending_check",
        status="ok",
        signals_24h=500,
        active_sources=67,
        detail="scheduled run completed",
    )
    save_briefing_payload(
        BriefingPayload(
            active_sources=67,
            signals_24h=500,
            top_signals=[signal],
            source_health={"Reddit JSON": "live (40)"},
            analysis_artifacts={"llm_generated_insight": {"status": "generated"}},
            llm_status="ollama:qwen2.5:0.5b",
            collection_mode="live",
        ),
        cache_path,
    )
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                f"INTERNET_RADAR_PAYLOAD_CACHE={cache_path}",
                "INTERNET_RADAR_DISPATCH_ALERTS=1",
                "INTERNET_RADAR_NTFY_TOPIC=radar-test",
                "INTERNET_RADAR_VECTOR_BACKEND=gemini",
                "GEMINI_API_KEY=gemini-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INTERNET_RADAR_PAYLOAD_CACHE", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_DISPATCH_ALERTS", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_NTFY_TOPIC", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_VECTOR_BACKEND", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    main(["--readiness", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)
    statuses = {check["key"]: check["status"] for check in output["checks"]}

    assert statuses["alert_dispatch"] == "ready"
    assert statuses["semantic_vectors"] == "ready"
    assert output["blockers"] == ["reddit_oauth", "telegram"]


def test_cli_readiness_does_not_leak_loaded_env_after_main_returns(tmp_path, monkeypatch, capsys):
    from internet_radar.cli import main
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.payload_cache import save_briefing_payload

    db_path = tmp_path / "radar.sqlite"
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=92,
        metadata={"stars": 1200},
    )
    RadarStore(db_path).record_signal_snapshots([signal])
    save_briefing_payload(
        BriefingPayload(
            active_sources=67,
            signals_24h=500,
            top_signals=[signal],
            source_health={"Reddit JSON": "live (40)"},
            analysis_artifacts={"llm_generated_insight": {"status": "generated"}},
            llm_status="ollama:qwen2.5:0.5b",
            collection_mode="live",
        ),
        tmp_path / "payload.json",
    )
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                f"INTERNET_RADAR_PAYLOAD_CACHE={tmp_path / 'payload.json'}",
                "INTERNET_RADAR_DISPATCH_ALERTS=1",
                "INTERNET_RADAR_NTFY_TOPIC=radar-test",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("INTERNET_RADAR_PAYLOAD_CACHE", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_DISPATCH_ALERTS", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_NTFY_TOPIC", raising=False)

    main(["--readiness", "--db", str(db_path)])
    capsys.readouterr()

    assert "INTERNET_RADAR_PAYLOAD_CACHE" not in os.environ
    assert "INTERNET_RADAR_DISPATCH_ALERTS" not in os.environ
    assert "INTERNET_RADAR_NTFY_TOPIC" not in os.environ


def test_cli_readiness_verify_external_runs_credential_checks(tmp_path, monkeypatch, capsys):
    from internet_radar.cli import main

    calls: list[str] = []

    def fake_reddit_check():
        calls.append("reddit")
        return {
            "configured": True,
            "valid": False,
            "detail": "401 invalid_client",
            "token_type": "",
        }

    def fake_telegram_check():
        calls.append("telegram")
        return {
            "configured": True,
            "valid": True,
            "detail": "chat resolved",
            "chat": {"chat_id": "12345", "type": "private", "name": "deepak"},
        }

    monkeypatch.setattr("internet_radar.cli.verify_reddit_oauth", fake_reddit_check)
    monkeypatch.setattr("internet_radar.cli.verify_telegram_credentials", fake_telegram_check)

    main(["--readiness", "--verify-external", "--db", str(tmp_path / "radar.sqlite")])

    output = json.loads(capsys.readouterr().out)
    checks = {check["key"]: check for check in output["checks"]}

    assert calls == ["reddit", "telegram"]
    assert output["external_verification"] is True
    assert checks["reddit_oauth"]["status"] == "blocked"
    assert checks["reddit_oauth"]["detail"] == "401 invalid_client"
    assert checks["telegram"]["status"] == "ready"
    assert checks["telegram"]["detail"] == "chat resolved"


def test_cli_test_alert_dispatches_to_ready_channels_and_reports_json(tmp_path, monkeypatch, capsys):
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.cli import main

    calls: list[object] = []

    def fake_dispatch(alert, **kwargs):
        calls.append((alert, kwargs))
        return [AlertDispatchResult(channel=channel, sent=True, detail="sent") for channel in alert.channels]

    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "chat")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.setattr("internet_radar.cli.dispatch_alert", fake_dispatch)

    main(["--test-alert", "--db", str(tmp_path / "radar.sqlite")])

    output = json.loads(capsys.readouterr().out)
    alert, kwargs = calls[0]

    assert output["test_alert"] is True
    assert output["channels"] == ["ntfy", "telegram"]
    assert [(result["channel"], result["sent"]) for result in output["results"]] == [("ntfy", True), ("telegram", True)]
    assert alert.kind == "TEST_ALERT"
    assert alert.channels == ["ntfy", "telegram"]
    assert "Internet Radar test alert" in alert.body
    assert kwargs["outbox_db_path"] == tmp_path / "radar.sqlite"


def test_cli_test_alert_reports_failed_forced_channel_without_claiming_sent(tmp_path, monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setenv("INTERNET_RADAR_DISABLE_DOTENV", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    main(["--test-alert", "--alert-channel", "telegram", "--db", str(tmp_path / "radar.sqlite")])

    output = json.loads(capsys.readouterr().out)

    assert output["channels"] == ["telegram"]
    assert output["results"] == [{"channel": "telegram", "sent": False, "detail": "missing telegram credentials"}]
    assert output["detail"] == "completed with failures"


def test_cli_alert_outbox_compact_reports_deleted_and_pending_counts(tmp_path, capsys):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.cli import main

    db_path = tmp_path / "radar.sqlite"
    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )
    outbox = AlertOutbox(db_path)
    outbox.enqueue(alert, channel="ntfy", detail="network error: Timeout")
    outbox.enqueue(alert, channel="ntfy", detail="network error: ConnectTimeout", coalesce=False)

    main(["--alert-outbox-compact", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "alert_outbox_compact": True,
        "deleted": 1,
        "pending_count": 1,
    }


def test_cli_retry_alerts_reports_attempted_results_and_skips_unready(tmp_path, monkeypatch, capsys):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.cli import main

    db_path = tmp_path / "radar.sqlite"
    outbox = AlertOutbox(db_path)
    outbox.record_results(
        AlertMessage(
            signal_id="skill-ntfy",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright",
            channels=["ntfy"],
            score=94,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )
    outbox.record_results(
        AlertMessage(
            signal_id="skill-telegram",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright",
            channels=["telegram"],
            score=94,
        ),
        [AlertDispatchResult(channel="telegram", sent=False, detail="missing telegram credentials")],
    )
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("INTERNET_RADAR_DISABLE_DOTENV", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    monkeypatch.setattr("internet_radar.alerts.dispatcher.send_ntfy", lambda **kwargs: True)

    main(["--retry-alerts", "--alert-retry-limit", "10", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)

    assert output["retry_alerts"] is True
    assert output["attempted_count"] == 1
    assert output["pending_count"] == 1
    assert output["results"] == [{"channel": "ntfy", "sent": True, "detail": "sent"}]


def test_cli_retry_alerts_respects_outbox_backoff_by_default(tmp_path, monkeypatch, capsys):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.cli import main

    db_path = tmp_path / "radar.sqlite"
    outbox = AlertOutbox(db_path)
    outbox.record_results(
        AlertMessage(
            signal_id="skill-ntfy",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright",
            channels=["ntfy"],
            score=94,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE alert_outbox SET attempts = 3, updated_at = ? WHERE signal_id = ?",
            (datetime.now(UTC).isoformat(), "skill-ntfy"),
        )
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setattr("internet_radar.alerts.dispatcher.send_ntfy", lambda **kwargs: calls.append(kwargs) or True)

    main(["--retry-alerts", "--alert-retry-limit", "10", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)
    pending = AlertOutbox(db_path).list_pending()

    assert output["retry_alerts"] is True
    assert output["attempted_count"] == 0
    assert output["pending_count"] == 1
    assert output["results"] == []
    assert calls == []
    assert pending[0].attempts == 3


def test_cli_retry_alerts_force_flag_overrides_outbox_backoff(tmp_path, monkeypatch, capsys):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.cli import main

    db_path = tmp_path / "radar.sqlite"
    outbox = AlertOutbox(db_path)
    outbox.record_results(
        AlertMessage(
            signal_id="skill-ntfy",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright",
            channels=["ntfy"],
            score=94,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE alert_outbox SET attempts = 3, updated_at = ? WHERE signal_id = ?",
            (datetime.now(UTC).isoformat(), "skill-ntfy"),
        )
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setattr("internet_radar.alerts.dispatcher.send_ntfy", lambda **kwargs: True)

    main(["--retry-alerts", "--force-alert-retry", "--alert-retry-limit", "10", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)

    assert output["retry_alerts"] is True
    assert output["attempted_count"] == 1
    assert output["pending_count"] == 0
    assert output["results"] == [{"channel": "ntfy", "sent": True, "detail": "sent"}]


def test_cli_digest_alerts_sends_summary_for_ready_channel(tmp_path, monkeypatch, capsys):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox
    from internet_radar.cli import main

    db_path = tmp_path / "radar.sqlite"
    outbox = AlertOutbox(db_path)
    outbox.record_results(
        AlertMessage(
            signal_id="skill-ntfy",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright",
            channels=["ntfy"],
            score=94,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setattr("internet_radar.alerts.dispatcher.send_ntfy", lambda **kwargs: True)

    main(["--digest-alerts", "--alert-channel", "ntfy", "--db", str(db_path)])

    output = json.loads(capsys.readouterr().out)

    assert output["digest_alerts"] is True
    assert output["pending_count"] == 0
    assert output["results"] == [{"channel": "ntfy", "sent": True, "detail": "sent"}]


def test_cli_telegram_chats_prints_discovered_chat_ids(monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setattr(
        "internet_radar.cli.discover_telegram_chats",
        lambda token: [{"chat_id": "12345", "type": "private", "name": "deepak"}],
    )

    main(["--telegram-chats"])

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "telegram_chat_discovery": True,
        "chats": [{"chat_id": "12345", "type": "private", "name": "deepak"}],
        "detail": "set TELEGRAM_CHAT_ID to one of the discovered chat_id values",
    }


def test_cli_telegram_check_prints_no_send_credential_verification(monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    monkeypatch.setattr(
        "internet_radar.cli.verify_telegram_credentials",
        lambda: {
            "configured": True,
            "valid": True,
            "detail": "chat resolved",
            "chat": {"chat_id": "12345", "type": "private", "name": "deepak"},
        },
    )

    main(["--telegram-check"])

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "telegram_check": True,
        "configured": True,
        "valid": True,
        "detail": "chat resolved",
        "chat": {"chat_id": "12345", "type": "private", "name": "deepak"},
    }


def test_cli_ntfy_check_prints_delivery_probe(monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setattr(
        "internet_radar.cli.verify_ntfy_delivery",
        lambda: {
            "configured": True,
            "valid": False,
            "detail": "network error: ConnectTimeout",
            "server": "https://ntfy.sh",
        },
    )

    main(["--ntfy-check"])

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "ntfy_check": True,
        "configured": True,
        "valid": False,
        "detail": "network error: ConnectTimeout",
        "server": "https://ntfy.sh",
    }


def test_cli_credential_setup_reports_remaining_external_steps_without_secret_values(monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-secret-topic")
    monkeypatch.setenv("REDDIT_CLIENT_ID", "reddit-client-value")
    monkeypatch.setenv("INTERNET_RADAR_DISABLE_DOTENV", "1")
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    main(["--credential-setup"])

    raw_output = capsys.readouterr().out
    output = json.loads(raw_output)
    items = {item["key"]: item for item in output["items"]}

    assert output["credential_setup"] is True
    assert output["ready_count"] == 1
    assert output["blocked_count"] == 2
    assert items["ntfy"]["status"] == "ready"
    assert items["reddit_oauth"]["status"] == "blocked"
    assert items["reddit_oauth"]["missing_env"] == ["REDDIT_CLIENT_SECRET"]
    assert items["reddit_oauth"]["app_type"] == "script"
    assert items["reddit_oauth"]["redirect_uri"] == "http://localhost:8080"
    assert items["telegram"]["missing_env"] == ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    assert "reddit-client-value" not in raw_output
    assert "radar-secret-topic" not in raw_output


def test_cli_reddit_check_prints_oauth_verification(monkeypatch, capsys):
    from internet_radar.cli import main

    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        "internet_radar.cli.verify_reddit_oauth",
        lambda: {"configured": True, "valid": True, "detail": "token acquired", "token_type": "bearer"},
    )

    main(["--reddit-check"])

    output = json.loads(capsys.readouterr().out)

    assert output == {
        "reddit_oauth_check": True,
        "configured": True,
        "valid": True,
        "detail": "token acquired",
        "token_type": "bearer",
    }
