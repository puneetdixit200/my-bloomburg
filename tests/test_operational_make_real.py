from __future__ import annotations

from datetime import UTC, datetime, timedelta

from internet_radar.storage.models import SignalRecord, UserProfile


def test_store_records_numeric_signal_snapshots_and_history(tmp_path):
    from internet_radar.storage.db import RadarStore

    store = RadarStore(tmp_path / "radar.sqlite")
    observed_at = datetime(2026, 5, 26, 9, 0, tzinfo=UTC)
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=82,
        velocity=120,
        observed_at=observed_at,
        metadata={"stars": 1200, "language": "Python", "funded": False},
    )

    inserted = store.record_signal_snapshots([signal], run_id="test-run", observed_at=observed_at)
    star_history = store.metric_history(signal_id="repo:agent", metric="stars")
    score_history = store.metric_history(topic="browser agents", metric="score")

    assert inserted == 3
    assert star_history[0].run_id == "test-run"
    assert star_history[0].value == 1200
    assert score_history[0].value == 82
    assert "002_signal_snapshots" in store.schema_versions()


def test_historical_velocity_compares_current_to_three_and_seven_day_baselines(tmp_path):
    from internet_radar.signals.velocity_engine import historical_trend_for_signal
    from internet_radar.storage.db import RadarStore

    store = RadarStore(tmp_path / "radar.sqlite")
    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    signal = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=90,
        velocity=0,
        observed_at=now,
        metadata={"stars": 1900},
    )
    for days, stars in [(7, 1000), (3, 1300), (0, 1900)]:
        store.record_signal_snapshots(
            [
                signal.model_copy(
                    update={
                        "observed_at": now - timedelta(days=days),
                        "metadata": {"stars": stars},
                    }
                )
            ],
            run_id=f"run-{days}",
            observed_at=now - timedelta(days=days),
        )

    trend = historical_trend_for_signal(signal, store.metric_history(signal_id="repo:agent", metric="stars"), now=now)

    assert trend.metric == "stars"
    assert trend.current_value == 1900
    assert trend.value_3d_ago == 1300
    assert trend.value_7d_ago == 1000
    assert trend.delta_3d == 600
    assert trend.acceleration_3d_per_day == 200
    assert trend.delta_7d == 900
    assert trend.direction == "up"
    assert trend.velocity_score == 46


def test_pipeline_persists_snapshots_historical_trends_and_analysis_artifacts(tmp_path):
    from internet_radar.pipeline import run_radar_once
    from internet_radar.storage.db import RadarStore

    now = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
    db_path = tmp_path / "radar.sqlite"
    store = RadarStore(db_path)
    old = SignalRecord(
        id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        score=72,
        velocity=0,
        observed_at=now - timedelta(days=3),
        metadata={"stars": 1000},
    )
    store.upsert_signals([old])
    store.record_signal_snapshots([old], run_id="old", observed_at=old.observed_at)

    class FakeCollector:
        name = "GitHub Search"
        category = "code"

        def collect(self):
            return [
                SignalRecord(
                    id="repo:agent",
                    topic="browser agents",
                    title="Browser agent repo",
                    source=self.name,
                    category=self.category,
                    score=88,
                    velocity=0,
                    observed_at=now,
                    metadata={"stars": 1300},
                )
            ]

    result = run_radar_once(collectors=[FakeCollector()], db_path=db_path, use_live_network=False, now=now)

    assert result.historical_trends[0].metric == "stars"
    assert result.historical_trends[0].acceleration_3d_per_day == 100
    assert result.analysis_artifacts["daily_briefing"]["headline"] == "browser agents"
    assert result.analysis_artifacts["trend_predictions"]
    assert RadarStore(db_path).metric_history(signal_id="repo:agent", metric="stars")[0].value == 1300


def test_scheduler_uses_persistent_sqlite_job_store(tmp_path):
    from internet_radar.scheduler.runner import build_scheduler

    scheduler = build_scheduler(job_runner="internet_radar.scheduler.runner:run_named_job", jobstore_path=tmp_path / "jobs.sqlite")

    assert "default" in scheduler._jobstores
    assert scheduler._jobstores["default"].__class__.__name__ == "SQLAlchemyJobStore"
    assert str(tmp_path / "jobs.sqlite") in str(scheduler._jobstores["default"].engine.url)


def test_alert_readiness_reports_missing_free_channels_and_free_only_email(monkeypatch):
    from internet_radar.alerts.dispatcher import alert_readiness

    monkeypatch.setenv("INTERNET_RADAR_FREE_ONLY", "1")
    monkeypatch.delenv("INTERNET_RADAR_NTFY_TOPIC", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    readiness = {item.channel: item for item in alert_readiness()}

    assert readiness["ntfy"].ready is False
    assert readiness["telegram"].ready is False
    assert readiness["email"].ready is False
    assert readiness["email"].detail == "disabled by free-only mode"


def test_profile_is_more_personalized_and_threshold_is_seventy():
    from internet_radar.config.settings import load_user_profile

    profile = load_user_profile()

    assert profile.alert_threshold == 70
    assert {"python", "streamlit", "automation", "github", "data analysis"} <= set(profile.skills)
    assert "find internships with low competition" in profile.goals


def test_gap_patterns_cover_more_actionable_pain_categories():
    from internet_radar.config.settings import load_gap_patterns

    patterns = load_gap_patterns()

    assert {"privacy", "onboarding", "integration", "pricing"} <= set(patterns["categories"])
    assert "no api" in patterns["phrases"]
    assert patterns["weights"]["privacy"] >= 3


def test_reddit_api_collector_is_added_only_when_free_credentials_exist(monkeypatch):
    from internet_radar.collectors.live import default_collectors

    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert "Reddit API" in names


def test_dashboard_payload_passes_through_pipeline_operational_analysis():
    from internet_radar.dashboard_data import build_dashboard_payload
    from internet_radar.storage.models import HistoricalTrend

    trend = HistoricalTrend(
        signal_id="repo:agent",
        topic="browser agents",
        title="Browser agent repo",
        source="GitHub Search",
        category="code",
        metric="stars",
        current_value=1300,
        previous_value=1000,
        value_3d_ago=1000,
        value_7d_ago=None,
        delta_3d=300,
        delta_7d=None,
        acceleration_3d_per_day=100,
        acceleration_7d_per_day=None,
        direction="up",
        velocity_score=30,
        confidence=70,
        observed_at=datetime(2026, 5, 26, tzinfo=UTC),
    )
    payload = build_dashboard_payload(
        [SignalRecord(id="repo:agent", topic="browser agents", title="Browser agent repo", source="GitHub Search", category="code")],
        profile=UserProfile(),
        historical_trends=[trend],
        analysis_artifacts={"daily_briefing": {"headline": "browser agents"}, "analysis_route": "ollama:qwen2.5"},
    )

    assert payload["trend_velocity"]["historical_trends"][0].metric == "stars"
    assert payload["briefing"]["analysis_artifacts"]["daily_briefing"]["headline"] == "browser agents"
