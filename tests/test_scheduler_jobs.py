from __future__ import annotations

from datetime import UTC, datetime, timedelta

from internet_radar.storage.models import SignalRecord


def test_scheduler_job_plan_matches_architecture_cadences():
    from internet_radar.scheduler.jobs import build_job_plan

    plan = build_job_plan()
    by_group = {group.name: group for group in plan.groups}

    assert len(plan.jobs) == 32
    assert [job.name for job in by_group["high_frequency"].jobs] == [
        "github_trending_check",
        "hackathon_deadline_check",
        "career_page_watcher",
        "hn_frontpage_check",
        "alert_outbox_retry",
    ]
    assert by_group["high_frequency"].jobs[0].trigger == "interval"
    assert by_group["high_frequency"].jobs[0].minutes == 15
    assert "remoteok_jobs" in {job.name for job in by_group["hourly"].jobs}
    assert "cross_source_validation" in {job.name for job in by_group["six_hourly"].jobs}
    weekly = next(job for job in by_group["daily"].jobs if job.name == "weekly_trend_report")
    assert weekly.trigger == "cron"
    assert weekly.hour == 7
    assert weekly.day_of_week == "mon"


def test_smart_triggers_flag_score_multi_source_and_hackathon_crowd_jump():
    from internet_radar.scheduler.jobs import smart_triggers_for_signals

    now = datetime.now(UTC)
    signals = [
        SignalRecord(
            id="score",
            topic="browser agents",
            title="Browser agents exploding",
            source="GitHub",
            category="code",
            score=94,
            observed_at=now,
        ),
        SignalRecord(id="a", topic="mcp", title="MCP on HN", source="HN", category="social", score=70, observed_at=now),
        SignalRecord(id="b", topic="mcp", title="MCP repos", source="GitHub", category="code", score=71, observed_at=now - timedelta(minutes=30)),
        SignalRecord(id="c", topic="mcp", title="MCP jobs", source="RemoteOK", category="jobs", score=72, observed_at=now - timedelta(minutes=55)),
        SignalRecord(
            id="hack",
            topic="agent hackathon",
            title="Agent Hack",
            source="Devpost",
            category="hackathons",
            score=80,
            observed_at=now,
            metadata={"participant_growth_pct": 60},
        ),
    ]

    triggers = smart_triggers_for_signals(signals, now=now)
    reasons = {(trigger.signal_id, trigger.reason) for trigger in triggers}

    assert ("score", "score_gt_90") in reasons
    assert ("c", "topic_hits_3_sources_1h") in reasons
    assert ("hack", "hackathon_crowd_jump") in reasons


def test_priority_queue_runs_high_signal_tasks_before_routine_jobs():
    from internet_radar.scheduler.jobs import ScheduledJob, SmartTrigger
    from internet_radar.scheduler.priority_queue import build_priority_queue

    queue = build_priority_queue(
        triggers=[
            SmartTrigger(signal_id="deep", topic="mcp", reason="topic_hits_3_sources_1h", action="deep_analysis"),
            SmartTrigger(signal_id="alert", topic="browser agents", reason="score_gt_90", action="immediate_alert"),
            SmartTrigger(signal_id="crowd", topic="agent hackathon", reason="hackathon_crowd_jump", action="crowd_alert"),
        ],
        routine_jobs=[
            ScheduledJob("reddit_collector", "interval", hours=1),
            ScheduledJob("daily_briefing_generate", "cron", hour=6),
        ],
    )

    ordered = queue.drain()

    assert [task.name for task in ordered] == [
        "immediate_alert:alert",
        "deep_analysis:deep",
        "crowd_alert:crowd",
        "routine:reddit_collector",
        "routine:daily_briefing_generate",
    ]
    assert [task.priority for task in ordered] == sorted(task.priority for task in ordered)


def test_priority_queue_is_stable_for_equal_priority_tasks():
    from internet_radar.scheduler.jobs import SmartTrigger
    from internet_radar.scheduler.priority_queue import build_priority_queue

    queue = build_priority_queue(
        triggers=[
            SmartTrigger(signal_id="first", topic="mcp", reason="score_gt_90", action="immediate_alert"),
            SmartTrigger(signal_id="second", topic="agents", reason="score_gt_90", action="immediate_alert"),
        ]
    )

    assert [task.name for task in queue.drain()] == ["immediate_alert:first", "immediate_alert:second"]


def test_scheduler_runner_registers_architecture_jobs_with_apscheduler():
    from internet_radar.scheduler.jobs import build_job_plan
    from internet_radar.scheduler.runner import build_scheduler

    scheduler = build_scheduler(job_runner=lambda job_name: None)
    jobs = scheduler.get_jobs()
    by_id = {job.id: job for job in jobs}

    assert len(jobs) == len(build_job_plan().jobs) + 1
    assert "interval" in str(by_id["github_trending_check"].trigger)
    assert "cron" in str(by_id["daily_briefing_generate"].trigger)
    assert "weekly_trend_report" in by_id
    assert "scheduler_daemon_heartbeat" in by_id


def test_scheduler_main_records_daemon_heartbeat_before_start(monkeypatch, tmp_path):
    from internet_radar.scheduler.heartbeat import latest_scheduler_heartbeat
    from internet_radar.scheduler import runner

    db_path = tmp_path / "radar.sqlite"
    calls: list[str] = []

    class FakeScheduler:
        def get_jobs(self):
            return [object(), object()]

        def start(self):
            calls.append("start")

    monkeypatch.setenv("INTERNET_RADAR_DB", str(db_path))
    monkeypatch.setattr(runner, "build_scheduler", lambda: FakeScheduler())

    runner.main(argv=[])

    heartbeat = latest_scheduler_heartbeat(db_path)

    assert calls == ["start"]
    assert heartbeat is not None
    assert heartbeat.job_name == "scheduler_daemon"
    assert heartbeat.status == "ok"
    assert heartbeat.active_sources == 2
    assert heartbeat.detail == "scheduler started"


def test_scheduler_runner_named_job_delegates_to_collector(monkeypatch, tmp_path):
    from internet_radar.scheduler.runner import run_named_job

    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))
    calls: list[str] = []

    def collect_once() -> int:
        calls.append("collected")
        return 14

    assert run_named_job("github_trending_check", collector=collect_once) == 14
    assert calls == ["collected"]


def test_scheduler_runner_once_cycle_records_manual_heartbeat(monkeypatch, tmp_path):
    from internet_radar.scheduler.heartbeat import latest_scheduler_heartbeat
    from internet_radar.scheduler.runner import run_cycle

    db_path = tmp_path / "radar.sqlite"
    monkeypatch.setenv("INTERNET_RADAR_DB", str(db_path))

    assert run_cycle(lambda: 21) == 21

    heartbeat = latest_scheduler_heartbeat(db_path)

    assert heartbeat is not None
    assert heartbeat.job_name == "manual_cycle"
    assert heartbeat.status == "ok"
    assert heartbeat.signals_24h == 21


def test_scheduler_runner_records_named_job_heartbeat(monkeypatch, tmp_path):
    from internet_radar.scheduler.heartbeat import latest_scheduler_heartbeat
    from internet_radar.scheduler.runner import run_named_job

    db_path = tmp_path / "radar.sqlite"
    monkeypatch.setenv("INTERNET_RADAR_DB", str(db_path))

    assert run_named_job("github_trending_check", collector=lambda: 14) == 14

    heartbeat = latest_scheduler_heartbeat(db_path)

    assert heartbeat is not None
    assert heartbeat.job_name == "github_trending_check"
    assert heartbeat.status == "ok"
    assert heartbeat.signals_24h == 14


def test_scheduler_named_jobs_have_specific_live_collector_groups():
    from internet_radar.scheduler.jobs import collectors_for_job

    assert [collector.name for collector in collectors_for_job("github_trending_check", use_live_network=True)] == ["GitHub Trending"]
    assert {collector.name for collector in collectors_for_job("pypi_npm_velocity", use_live_network=True)} >= {
        "PyPI",
        "npm Registry",
        "crates.io",
    }
    assert {collector.name for collector in collectors_for_job("app_store_pain_mining", use_live_network=True)} == {
        "iTunes App Store",
        "Google Play",
        "Steam",
    }


def test_scheduler_alert_dispatches_use_durable_outbox(monkeypatch, tmp_path):
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.scheduler import jobs
    from internet_radar.storage.models import BriefingPayload, UserProfile

    calls: list[object] = []

    def fake_dispatch(alert, **kwargs):
        calls.append(kwargs.get("outbox_db_path"))
        return [AlertDispatchResult(channel=alert.channels[0], sent=False, detail="network error: Timeout")]

    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.setattr(jobs, "load_user_profile", lambda: UserProfile(alert_threshold=80, notification_channels=["ntfy"]))
    monkeypatch.setattr(jobs, "dispatch_alert", fake_dispatch)

    briefing = BriefingPayload(
        active_sources=1,
        signals_24h=1,
        top_signals=[
            SignalRecord(
                id="hot",
                topic="browser agents",
                title="Browser agents spike",
                source="GitHub",
                category="code",
                score=95,
            )
        ],
    )

    results = jobs._maybe_dispatch_alerts(briefing, dispatch_alerts=True)

    assert results[0].sent is False
    assert calls == [tmp_path / "radar.sqlite"]


def test_scheduler_alert_dispatch_filters_unready_profile_channels(monkeypatch, tmp_path):
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.scheduler import jobs
    from internet_radar.storage.models import BriefingPayload, UserProfile

    dispatched_channels: list[list[str]] = []

    def fake_dispatch(alert, **kwargs):
        dispatched_channels.append(alert.channels)
        return [AlertDispatchResult(channel=channel, sent=True, detail="sent") for channel in alert.channels]

    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))
    monkeypatch.setenv("INTERNET_RADAR_NTFY_TOPIC", "radar-test")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(jobs, "load_user_profile", lambda: UserProfile(alert_threshold=80, notification_channels=["ntfy", "telegram"]))
    monkeypatch.setattr(jobs, "dispatch_alert", fake_dispatch)

    briefing = BriefingPayload(
        active_sources=1,
        signals_24h=1,
        top_signals=[
            SignalRecord(
                id="hot",
                topic="browser agents",
                title="Browser agents spike",
                source="GitHub",
                category="code",
                score=95,
            )
        ],
    )

    results = jobs._maybe_dispatch_alerts(briefing, dispatch_alerts=True)

    assert [result.channel for result in results] == ["ntfy"]
    assert dispatched_channels == [["ntfy"]]


def test_alert_outbox_retry_job_uses_outbox_without_collecting(monkeypatch, tmp_path):
    from internet_radar.alerts.dispatcher import AlertDispatchResult
    from internet_radar.scheduler import jobs

    calls: list[object] = []

    class FakeOutbox:
        def __init__(self, db_path):
            calls.append(db_path)

        def retry_pending(self, limit):
            calls.append(("retry", limit))
            return [AlertDispatchResult(channel="ntfy", sent=True, detail="sent")]

    monkeypatch.setenv("INTERNET_RADAR_DB", str(tmp_path / "radar.sqlite"))
    monkeypatch.setattr(jobs, "AlertOutbox", FakeOutbox)

    result = jobs.run_scheduled_job("alert_outbox_retry")

    assert result.job_name == "alert_outbox_retry"
    assert result.active_sources == 0
    assert result.signals_24h == 0
    assert [(dispatch.channel, dispatch.sent) for dispatch in result.alert_dispatches] == [("ntfy", True)]
    assert calls == [tmp_path / "radar.sqlite", ("retry", 25)]
