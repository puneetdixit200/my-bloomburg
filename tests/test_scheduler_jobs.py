from __future__ import annotations

from datetime import UTC, datetime, timedelta

from internet_radar.storage.models import SignalRecord


def test_scheduler_job_plan_matches_architecture_cadences():
    from internet_radar.scheduler.jobs import build_job_plan

    plan = build_job_plan()
    by_group = {group.name: group for group in plan.groups}

    assert len(plan.jobs) == 31
    assert [job.name for job in by_group["high_frequency"].jobs] == [
        "github_trending_check",
        "hackathon_deadline_check",
        "career_page_watcher",
        "hn_frontpage_check",
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
