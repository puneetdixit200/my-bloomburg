from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from internet_radar.storage.models import SignalRecord, UserProfile


def test_format_alert_uses_architecture_template_for_hackathon():
    from internet_radar.alerts.alert_manager import format_alert

    signal = SignalRecord(
        id="hack-1",
        topic="agent hackathon",
        title="NVIDIA AI Hack",
        source="Devpost",
        category="hackathons",
        url="https://example.com/hack",
        score=91,
        metadata={
            "prize": 50000,
            "participants": 67,
            "days_left": 12,
            "remote": True,
            "sponsors": ["NVIDIA"],
            "theme": "AI agents",
            "reasoning": "Strong sponsor fit and short deadline.",
        },
    )

    alert = format_alert(signal)

    assert alert.kind == "HACKATHON"
    assert alert.title == "HIGH OPPORTUNITY - HACKATHON"
    assert "NVIDIA AI Hack" in alert.body
    assert "Prize: $50,000" in alert.body
    assert "Deadline: 12 days" in alert.body
    assert "SCORE: 91/100" in alert.body
    assert "https://example.com/hack" in alert.body


def test_build_alerts_filters_by_profile_threshold_and_channels():
    from internet_radar.alerts.alert_manager import build_alerts

    profile = UserProfile(alert_threshold=80, notification_channels=["ntfy", "telegram"])
    hot = SignalRecord(
        id="skill-1",
        topic="mcp servers",
        title="MCP servers skill demand rising",
        source="Skill Radar",
        category="jobs",
        score=74,
        metadata={"relevance_score": 88, "skill": "MCP servers", "job_growth": 280},
    )
    cold = SignalRecord(id="cold-1", topic="frontend", title="CSS library", source="Dev.to", category="news", score=70)

    alerts = build_alerts([cold, hot], profile)

    assert len(alerts) == 1
    assert alerts[0].signal_id == "skill-1"
    assert alerts[0].kind == "SKILL_RADAR"
    assert alerts[0].channels == ["ntfy", "telegram"]
    assert "Skill: MCP servers" in alerts[0].body


def test_format_alert_supports_research_funding_and_gap_templates():
    from internet_radar.alerts.alert_manager import format_alert

    research = format_alert(
        SignalRecord(
            id="research-1",
            topic="embodied ai",
            title="Embodied AI papers increase",
            source="arXiv",
            category="research",
            score=82,
            metadata={"papers_week": 18, "growth": 340, "recommended_skill": "robotics simulation"},
        )
    )
    funding = format_alert(
        SignalRecord(
            id="funding-1",
            topic="ai devtools",
            title="Code agents startup raises seed",
            source="YC",
            category="finance",
            score=86,
            metadata={"company": "Code Agents", "amount": 4_700_000, "sector": "developer tools"},
        )
    )
    gap = format_alert(
        SignalRecord(
            id="gap-1",
            topic="ai resume tools",
            title="Users complain about resume tools",
            source="Reddit JSON",
            category="social",
            score=84,
            metadata={"pain_level": 9, "complaint_count": 234, "best_quote": "Too much manual editing."},
        )
    )

    assert research.kind == "RESEARCH_SIGNAL"
    assert "SKILL TO LEARN: robotics simulation" in research.body
    assert funding.kind == "FUNDING_ALERT"
    assert "Amount: $4,700,000" in funding.body
    assert gap.kind == "STARTUP_GAP"
    assert "Complaints found: 234" in gap.body


def test_dashboard_payload_includes_profile_threshold_alerts():
    from internet_radar.dashboard_data import build_dashboard_payload

    profile = UserProfile(alert_threshold=85, notification_channels=["ntfy"])
    signal = SignalRecord(
        id="hack-2",
        topic="agent hackathon",
        title="Agent Hack",
        source="Devpost",
        category="hackathons",
        score=82,
        metadata={"relevance_score": 93, "prize": 10000, "days_left": 5},
    )

    payload = build_dashboard_payload([signal], active_sources=1, profile=profile)

    assert payload["briefing"]["alerts"][0].signal_id == "hack-2"
    assert payload["briefing"]["alerts"][0].channels == ["ntfy"]
    assert payload["briefing"]["alerts"][0].score == 93


def test_alert_templates_are_standalone_and_safe_for_missing_fields():
    from internet_radar.alerts.alert_templates import ALERT_TEMPLATES, render_alert_template

    signal = SignalRecord(
        id="funding-2",
        topic="agent devtools",
        title="Agent devtools seed round",
        source="SEC EDGAR",
        category="finance",
        score=89,
    )

    body = render_alert_template("FUNDING_ALERT", signal, score=91)

    assert {"HACKATHON", "STARTUP_GAP", "RESEARCH_SIGNAL", "FUNDING_ALERT", "SKILL_RADAR"} <= set(ALERT_TEMPLATES)
    assert "VC MONEY DETECTED -> SECTOR SIGNAL" in body
    assert "Company: Agent devtools seed round" in body
    assert "Amount: unknown" in body
    assert "SCORE: 91/100" in body


def test_alert_dispatcher_routes_all_configured_channels_without_real_network():
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        ok = True
        status_code = 200
        text = "ok"

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy", "telegram", "discord", "email"],
        score=94,
    )

    results = dispatch_alert(
        alert,
        config={
            "ntfy_topic": "radar-test",
            "telegram_bot_token": "token",
            "telegram_chat_id": "chat",
            "discord_webhook_url": "https://discord.example/webhook",
            "mailgun_domain": "mg.example.com",
            "mailgun_api_key": "key",
            "email_to": "me@example.com",
            "email_from": "radar@example.com",
        },
        http_post=fake_post,
    )

    assert [result.channel for result in results] == ["ntfy", "telegram", "discord", "email"]
    assert all(result.sent for result in results)
    assert calls[0][0] == "https://ntfy.sh/radar-test"
    assert calls[1][0] == "https://api.telegram.org/bottoken/sendMessage"
    assert calls[2][0] == "https://discord.example/webhook"
    assert calls[3][0] == "https://api.mailgun.net/v3/mg.example.com/messages"


def test_alert_dispatcher_skips_channels_without_credentials():
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["telegram", "discord", "email"],
        score=94,
    )

    results = dispatch_alert(alert, config={}, http_post=lambda *args, **kwargs: None)

    assert [result.channel for result in results] == ["telegram", "discord", "email"]
    assert not any(result.sent for result in results)
    assert all("missing" in result.detail for result in results)


def test_alert_dispatcher_reports_network_errors_without_raising():
    import requests

    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert

    def failing_post(*args, **kwargs):
        raise requests.exceptions.Timeout("network stalled")

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )

    results = dispatch_alert(alert, config={"ntfy_topic": "radar-test"}, http_post=failing_post)

    assert [(result.channel, result.sent) for result in results] == [("ntfy", False)]
    assert "network error" in results[0].detail


def test_alert_dispatcher_reports_telegram_api_error_details():
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert

    class FakeResponse:
        ok = False
        status_code = 429

        def json(self):
            return {"description": "Too Many Requests: retry after 60"}

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["telegram"],
        score=94,
    )

    results = dispatch_alert(
        alert,
        config={"telegram_bot_token": "token", "telegram_chat_id": "chat"},
        http_post=lambda *args, **kwargs: FakeResponse(),
    )

    assert [(result.channel, result.sent) for result in results] == [("telegram", False)]
    assert results[0].detail == "HTTP 429: Too Many Requests: retry after 60"


def test_ntfy_delivery_verifier_reports_missing_topic_without_network(monkeypatch):
    from internet_radar.alerts.ntfy_notifier import verify_ntfy_delivery

    calls: list[object] = []
    monkeypatch.delenv("INTERNET_RADAR_NTFY_TOPIC", raising=False)

    result = verify_ntfy_delivery(http_post=lambda *args, **kwargs: calls.append(args))

    assert calls == []
    assert result == {
        "configured": False,
        "valid": False,
        "detail": "missing INTERNET_RADAR_NTFY_TOPIC",
        "server": "https://ntfy.sh",
    }


def test_ntfy_delivery_verifier_reports_network_errors(monkeypatch):
    import requests

    from internet_radar.alerts.ntfy_notifier import verify_ntfy_delivery

    def failing_post(*args, **kwargs):
        raise requests.exceptions.ConnectTimeout("connect timed out")

    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_SERVER", "https://ntfy.sh")

    result = verify_ntfy_delivery(http_post=failing_post)

    assert result == {
        "configured": True,
        "valid": False,
        "detail": "network error: ConnectTimeout",
        "server": "https://ntfy.sh",
    }


def test_ntfy_delivery_verifier_reports_success(monkeypatch):
    from internet_radar.alerts.ntfy_notifier import verify_ntfy_delivery

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        ok = True

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setenv("INTERNET_RADAR_NTFY_SERVER", "https://ntfy.example")

    result = verify_ntfy_delivery(http_post=fake_post)

    assert result == {
        "configured": True,
        "valid": True,
        "detail": "sent",
        "server": "https://ntfy.example",
    }
    assert calls[0][0] == "https://ntfy.example/radar-test"
    assert b"Internet Radar ntfy delivery check" in calls[0][1]["data"]


def test_alert_dispatcher_records_failed_results_in_outbox(tmp_path):
    import requests

    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert
    from internet_radar.alerts.outbox import AlertOutbox

    def failing_post(*args, **kwargs):
        raise requests.exceptions.Timeout("network stalled")

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )

    results = dispatch_alert(
        alert,
        config={"ntfy_topic": "radar-test"},
        http_post=failing_post,
        outbox_db_path=tmp_path / "radar.sqlite",
    )
    pending = AlertOutbox(tmp_path / "radar.sqlite").list_pending()

    assert results[0].sent is False
    assert len(pending) == 1
    assert pending[0].signal_id == "skill-1"
    assert pending[0].channel == "ntfy"
    assert "network error" in pending[0].last_error


def test_alert_outbox_coalesces_repeated_pending_failures(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )
    outbox = AlertOutbox(tmp_path / "radar.sqlite")

    first_id = outbox.record_results(
        alert,
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )
    second_id = outbox.record_results(
        alert,
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: ConnectTimeout")],
    )
    pending = outbox.list_pending()

    assert first_id == 1
    assert second_id == 0
    assert len(pending) == 1
    assert pending[0].attempts == 2
    assert pending[0].last_error == "network error: ConnectTimeout"


def test_alert_outbox_compacts_existing_duplicate_pending_rows(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )
    outbox = AlertOutbox(tmp_path / "radar.sqlite")
    outbox.enqueue(alert, channel="ntfy", detail="network error: Timeout")
    outbox.enqueue(
        AlertMessage(
            signal_id="skill-1",
            kind="SKILL_RADAR",
            title="SKILL TO LEARN NOW",
            body="Skill: Playwright updated",
            channels=["ntfy"],
            score=96,
        ),
        channel="ntfy",
        detail="network error: ConnectTimeout",
        coalesce=False,
    )

    deleted = outbox.compact_pending()
    pending = outbox.list_pending()

    assert deleted == 1
    assert len(pending) == 1
    assert pending[0].attempts == 2
    assert pending[0].score == 96
    assert pending[0].body == "Skill: Playwright updated"
    assert pending[0].last_error == "network error: ConnectTimeout"


def test_alert_outbox_retry_skips_unready_channels_without_incrementing_attempts(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    outbox = AlertOutbox(tmp_path / "radar.sqlite")
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

    retry_results = outbox.retry_pending(config={}, http_post=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")))
    pending = outbox.list_pending()

    assert retry_results == []
    assert len(pending) == 1
    assert pending[0].attempts == 1
    assert pending[0].last_error == "missing telegram credentials"


def test_alert_outbox_retry_limit_counts_ready_attempts_not_skipped_rows(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    outbox = AlertOutbox(tmp_path / "radar.sqlite")
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

    class FakeResponse:
        ok = True

    retry_results = outbox.retry_pending(
        config={"ntfy_topic": "radar-test"},
        http_post=lambda *args, **kwargs: FakeResponse(),
        limit=1,
    )

    assert [(result.channel, result.sent) for result in retry_results] == [("ntfy", True)]


def test_alert_outbox_retry_respects_recent_failure_backoff(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    db_path = tmp_path / "radar.sqlite"
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    calls: list[object] = []
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
            (now.isoformat(), "skill-ntfy"),
        )

    retry_results = outbox.retry_pending(
        config={"ntfy_topic": "radar-test"},
        http_post=lambda *args, **kwargs: calls.append((args, kwargs)),
        now=now,
    )
    pending = outbox.list_pending()

    assert retry_results == []
    assert calls == []
    assert pending[0].attempts == 3
    assert pending[0].last_error == "network error: Timeout"


def test_alert_outbox_retry_force_overrides_recent_failure_backoff(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    db_path = tmp_path / "radar.sqlite"
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
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
            (now.isoformat(), "skill-ntfy"),
        )

    class FakeResponse:
        ok = True

    retry_results = outbox.retry_pending(
        config={"ntfy_topic": "radar-test"},
        http_post=lambda *args, **kwargs: FakeResponse(),
        respect_backoff=False,
        now=now,
    )

    assert [(result.channel, result.sent, result.detail) for result in retry_results] == [("ntfy", True, "sent")]
    assert outbox.list_pending() == []
    assert outbox.list_recent()[0].status == "sent"


def test_alert_outbox_retry_attempts_due_backoff_rows(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    db_path = tmp_path / "radar.sqlite"
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
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
            "UPDATE alert_outbox SET attempts = 2, updated_at = ? WHERE signal_id = ?",
            ((now - timedelta(minutes=5)).isoformat(), "skill-ntfy"),
        )

    class FakeResponse:
        ok = True

    retry_results = outbox.retry_pending(
        config={"ntfy_topic": "radar-test"},
        http_post=lambda *args, **kwargs: FakeResponse(),
        now=now,
    )

    assert [(result.channel, result.sent, result.detail) for result in retry_results] == [("ntfy", True, "sent")]
    assert outbox.list_pending() == []


def test_alert_outbox_digest_sends_one_summary_and_marks_channel_digested(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    db_path = tmp_path / "radar.sqlite"
    calls: list[tuple[str, dict[str, object]]] = []
    outbox = AlertOutbox(db_path)
    for signal_id in ["skill-1", "skill-2"]:
        outbox.record_results(
            AlertMessage(
                signal_id=signal_id,
                kind="SKILL_RADAR",
                title=f"Signal {signal_id}",
                body=f"Body {signal_id}",
                channels=["ntfy"],
                score=94,
            ),
            [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
        )

    class FakeResponse:
        ok = True

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    result = outbox.send_pending_digest(
        channel="ntfy",
        config={"ntfy_topic": "radar-test"},
        http_post=fake_post,
    )

    recent = outbox.list_recent(limit=10)

    assert result == AlertDispatchResult(channel="ntfy", sent=True, detail="sent")
    assert outbox.list_pending() == []
    assert [item.status for item in recent if item.channel == "ntfy"] == ["digested", "digested"]
    assert len(calls) == 1
    assert calls[0][0] == "https://ntfy.sh/radar-test"
    assert b"2 pending ntfy alerts" in calls[0][1]["data"]
    assert b"Signal skill-1" in calls[0][1]["data"]


def test_alert_outbox_digest_keeps_pending_rows_when_summary_delivery_fails(tmp_path):
    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.alerts.outbox import AlertOutbox

    outbox = AlertOutbox(tmp_path / "radar.sqlite")
    outbox.record_results(
        AlertMessage(
            signal_id="skill-1",
            kind="SKILL_RADAR",
            title="Signal skill-1",
            body="Body skill-1",
            channels=["ntfy"],
            score=94,
        ),
        [AlertDispatchResult(channel="ntfy", sent=False, detail="network error: Timeout")],
    )

    class FakeResponse:
        ok = False

    result = outbox.send_pending_digest(
        channel="ntfy",
        config={"ntfy_topic": "radar-test"},
        http_post=lambda *args, **kwargs: FakeResponse(),
    )

    assert result == AlertDispatchResult(channel="ntfy", sent=False, detail="failed")
    pending = outbox.list_pending()
    assert len(pending) == 1
    assert pending[0].last_error == "digest failed: failed"


def test_alert_outbox_retries_pending_and_marks_success(tmp_path):
    import requests

    from internet_radar.alerts.alert_manager import AlertMessage
    from internet_radar.alerts.dispatcher import dispatch_alert
    from internet_radar.alerts.outbox import AlertOutbox

    class FakeResponse:
        ok = True

    def failing_post(*args, **kwargs):
        raise requests.exceptions.Timeout("network stalled")

    alert = AlertMessage(
        signal_id="skill-1",
        kind="SKILL_RADAR",
        title="SKILL TO LEARN NOW",
        body="Skill: Playwright",
        channels=["ntfy"],
        score=94,
    )

    dispatch_alert(
        alert,
        config={"ntfy_topic": "radar-test"},
        http_post=failing_post,
        outbox_db_path=tmp_path / "radar.sqlite",
    )
    outbox = AlertOutbox(tmp_path / "radar.sqlite")

    retry_results = outbox.retry_pending(config={"ntfy_topic": "radar-test"}, http_post=lambda *args, **kwargs: FakeResponse())

    assert [(result.channel, result.sent, result.detail) for result in retry_results] == [("ntfy", True, "sent")]
    assert outbox.list_pending() == []
    assert outbox.list_recent()[0].status == "sent"


def test_telegram_chat_discovery_parses_get_updates_without_sending_messages():
    from internet_radar.alerts.telegram_bot import discover_telegram_chats

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        ok = True

        def json(self):
            return {
                "ok": True,
                "result": [
                    {
                        "message": {
                            "chat": {"id": 12345, "type": "private", "username": "deepak", "first_name": "Deepak"}
                        }
                    },
                    {
                        "channel_post": {
                            "chat": {"id": -10099, "type": "channel", "title": "Radar Alerts"}
                        }
                    },
                ],
            }

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    chats = discover_telegram_chats("token", http_get=fake_get)

    assert calls[0][0] == "https://api.telegram.org/bottoken/getUpdates"
    assert chats == [
        {"chat_id": "12345", "type": "private", "name": "deepak"},
        {"chat_id": "-10099", "type": "channel", "name": "Radar Alerts"},
    ]


def test_telegram_credential_verifier_uses_get_chat_without_sending_messages():
    from internet_radar.alerts.telegram_bot import verify_telegram_credentials

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        ok = True

        def json(self):
            return {"ok": True, "result": {"id": 12345, "type": "private", "username": "deepak"}}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    result = verify_telegram_credentials("token", "12345", http_get=fake_get)

    assert calls[0][0] == "https://api.telegram.org/bottoken/getChat"
    assert calls[0][1]["params"] == {"chat_id": "12345"}
    assert result == {
        "configured": True,
        "valid": True,
        "detail": "chat resolved",
        "chat": {"chat_id": "12345", "type": "private", "name": "deepak"},
    }


def test_telegram_credential_verifier_reports_missing_values_without_network():
    from internet_radar.alerts.telegram_bot import verify_telegram_credentials

    calls: list[object] = []

    result = verify_telegram_credentials("", "", http_get=lambda *args, **kwargs: calls.append(args))

    assert calls == []
    assert result == {
        "configured": False,
        "valid": False,
        "detail": "missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID",
        "chat": {},
    }
