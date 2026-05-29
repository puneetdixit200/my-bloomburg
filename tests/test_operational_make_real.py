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


def test_pipeline_analysis_can_generate_bounded_llm_insight(monkeypatch):
    from internet_radar.brain.llm_router import LLMChoice
    from internet_radar.brain.pipeline_analysis import build_analysis_artifacts

    monkeypatch.setenv("INTERNET_RADAR_ENABLE_LLM_ANALYSIS", "1")
    calls: list[dict[str, object]] = []

    class FakeRouter:
        def route(self, task, content_length):
            return LLMChoice(provider="ollama", model="fake-local", reason=f"test {task}")

        def classify_signal(self, text, allow_network=True):
            return {"topic": "browser agents", "sentiment": "negative", "confidence": 91}

        def generate_json(self, task, prompt, content_length=None, allow_network=True):
            calls.append(
                {
                    "task": task,
                    "prompt": prompt,
                    "content_length": content_length,
                    "allow_network": allow_network,
                }
            )
            return self.route(task, content_length or len(prompt)), {
                "headline": "Browser agents need better debugging",
                "narrative": "Complaints and code momentum point to a narrow devtools gap.",
                "opportunities": ["Build a browser-agent debugging copilot"],
                "risks": ["Validate beyond developer forums"],
                "actions": ["Interview five teams using browser automation"],
                "confidence": 86,
            }

    artifacts = build_analysis_artifacts(
        [
            SignalRecord(
                id="gap",
                topic="browser agents",
                title="Users complain browser agents are hard to debug",
                source="Reddit JSON",
                category="social",
                score=88,
                summary="Manual setup pain and opaque browser automation failures.",
                metadata={"frustration_score": 90},
            )
        ],
        active_sources=4,
        llm_status="ollama:fake-local",
        profile=UserProfile(skills=["python"]),
        router=FakeRouter(),
    )

    insight = artifacts["llm_generated_insight"]

    assert calls
    assert calls[0]["task"] == "daily_briefing"
    assert calls[0]["allow_network"] is True
    assert "Users complain browser agents" in str(calls[0]["prompt"])
    assert insight["status"] == "generated"
    assert insight["headline"] == "Browser agents need better debugging"
    assert insight["opportunities"] == ["Build a browser-agent debugging copilot"]
    assert insight["confidence"] == 86


def test_pipeline_analysis_only_sends_recent_signals_to_llm(monkeypatch):
    from internet_radar.brain.llm_router import LLMChoice
    from internet_radar.brain.pipeline_analysis import build_analysis_artifacts

    monkeypatch.setenv("INTERNET_RADAR_ENABLE_LLM_ANALYSIS", "1")
    monkeypatch.setenv("INTERNET_RADAR_SIGNAL_MAX_AGE_DAYS", "14")
    now = datetime.now(UTC)
    calls: list[str] = []

    class FakeRouter:
        def route(self, task, content_length):
            return LLMChoice(provider="ollama", model="fake-local", reason=f"test {task}")

        def classify_signal(self, text, allow_network=True):
            return {"topic": "fresh browser agents", "sentiment": "positive", "confidence": 80}

        def generate_json(self, task, prompt, content_length=None, allow_network=True):
            calls.append(prompt)
            return self.route(task, content_length or len(prompt)), {"headline": "Fresh only", "confidence": 81}

    build_analysis_artifacts(
        [
            SignalRecord(
                id="old",
                topic="old browser agents",
                title="Old browser-agent story",
                source="Old Source",
                category="news",
                score=100,
                observed_at=now.replace(year=2024),
            ),
            SignalRecord(
                id="fresh",
                topic="fresh browser agents",
                title="Fresh browser-agent story",
                source="Fresh Source",
                category="news",
                score=60,
                observed_at=now,
            ),
        ],
        active_sources=2,
        llm_status="ollama:fake-local",
        router=FakeRouter(),
    )

    assert calls
    assert "Fresh browser-agent story" in calls[0]
    assert "Old browser-agent story" not in calls[0]


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
    assert {
        "python",
        "ai",
        "streamlit",
        "automation",
        "robotics",
        "competitive coding",
        "nextjs",
        "fastapi",
    } <= set(profile.skills)
    assert {"browser agents", "local llm", "mcp", "internships", "hackathons", "ai agents", "open source", "yc startups"} <= set(
        profile.interests
    )
    assert "find internships with low competition" in profile.goals
    assert {"cryptocurrency", "nft", "web3"} <= set(profile.blocked_topics)
    assert {"ntfy", "telegram"} <= set(profile.notification_channels)


def test_gap_patterns_cover_more_actionable_pain_categories():
    from internet_radar.config.settings import load_gap_patterns

    patterns = load_gap_patterns()

    assert {"privacy", "onboarding", "integration", "pricing"} <= set(patterns["categories"])
    expected_patterns = {
        "too expensive",
        "overpriced",
        "pricing is ridiculous",
        "free alternative",
        "open source alternative",
        "why doesn't this exist",
        "i wish there was",
        "someone should build",
        "there's no good",
        "still no solution",
        "keeps crashing",
        "terrible ux",
        "documentation sucks",
        "support is awful",
        "abandoned project",
        "takes too long",
        "too many steps",
        "should be automated",
        "waste of time",
        "manual process",
    }
    assert expected_patterns <= set(patterns["phrases"]) | set(patterns["pain_terms"])
    assert patterns["weights"]["privacy"] >= 3


def test_reddit_api_collector_is_added_only_when_free_credentials_exist(monkeypatch):
    from internet_radar.collectors.live import default_collectors

    monkeypatch.setenv("REDDIT_CLIENT_ID", "client")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert "Reddit API" in names


def test_reddit_json_collector_scans_multiple_no_key_subreddits_without_oauth():
    from internet_radar.collectors.live import RedditJSONCollector

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, subreddit: str) -> None:
            self.subreddit = subreddit

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "id": f"{self.subreddit}-1",
                                "title": f"{self.subreddit} developer pain around browser agents",
                                "ups": 85,
                                "subreddit": self.subreddit,
                                "permalink": f"/r/{self.subreddit}/comments/1/topic/",
                            }
                        }
                    ]
                }
            }

    def fake_get(url, **kwargs):
        calls.append(url)
        subreddit = url.split("/r/", 1)[1].split("/", 1)[0]
        return FakeResponse(subreddit)

    collector = RedditJSONCollector(subreddits=["LocalLLaMA", "MachineLearning"])
    collector.http_get = fake_get
    collector.rate_limiter = None

    records = collector.collect()

    assert calls == [
        "https://www.reddit.com/r/LocalLLaMA/hot.json",
        "https://www.reddit.com/r/MachineLearning/hot.json",
    ]
    assert [record.metadata["subreddit"] for record in records] == ["LocalLLaMA", "MachineLearning"]


def test_reddit_oauth_verifier_reports_valid_credentials_without_collecting_posts():
    from internet_radar.collectors.live import verify_reddit_oauth

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "token", "token_type": "bearer", "expires_in": 3600}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    result = verify_reddit_oauth(client_id="client", client_secret="secret", http_post=fake_post)

    assert calls[0][0] == "https://www.reddit.com/api/v1/access_token"
    assert calls[0][1]["auth"] == ("client", "secret")
    assert result == {
        "configured": True,
        "valid": True,
        "detail": "token acquired",
        "token_type": "bearer",
    }


def test_reddit_oauth_verifier_reports_missing_credentials_without_network():
    from internet_radar.collectors.live import verify_reddit_oauth

    calls: list[object] = []

    result = verify_reddit_oauth(client_id="", client_secret="", http_post=lambda *args, **kwargs: calls.append(args))

    assert calls == []
    assert result == {
        "configured": False,
        "valid": False,
        "detail": "missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET",
        "token_type": "",
    }


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


def test_dashboard_payload_prefers_pipeline_analysis_artifacts():
    from internet_radar.dashboard_data import build_dashboard_payload

    artifacts = {
        "signal_summary": {"headline": "Pipeline summary", "next_action": "Act from cached analysis."},
        "classifications": [{"signal_id": "repo:agent", "topic": "pipeline topic"}],
        "gap_analyses": [{"topic": "pipeline gap", "startup_ideas": [{"idea": "Build the pipeline idea"}]}],
        "trend_predictions": [{"topic": "pipeline trend", "confidence": 91}],
        "idea_validations": [{"idea": "Pipeline idea", "score": 82}],
        "daily_briefing": {"headline": "Pipeline brief", "narrative": "Use the pipeline-generated brief."},
        "llm_generated_insight": {"headline": "Pipeline LLM insight", "status": "generated"},
    }
    payload = build_dashboard_payload(
        [SignalRecord(id="repo:agent", topic="browser agents", title="Browser agent repo", source="GitHub Search", category="code")],
        profile=UserProfile(),
        analysis_artifacts=artifacts,
    )

    briefing = payload["briefing"]

    assert briefing["signal_summary"] == artifacts["signal_summary"]
    assert briefing["classifications"] == artifacts["classifications"]
    assert briefing["gap_analyses"] == artifacts["gap_analyses"]
    assert briefing["trend_predictions"] == artifacts["trend_predictions"]
    assert briefing["idea_validations"] == artifacts["idea_validations"]
    assert briefing["daily_briefing"] == artifacts["daily_briefing"]
    assert briefing["llm_generated_insight"] == artifacts["llm_generated_insight"]
