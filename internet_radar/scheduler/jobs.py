from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from internet_radar.pipeline import run_radar_once
from internet_radar.storage.models import SignalRecord


@dataclass(frozen=True)
class ScheduledJob:
    name: str
    trigger: str
    minutes: int | None = None
    hours: int | None = None
    hour: int | None = None
    day_of_week: str | None = None


@dataclass(frozen=True)
class JobGroup:
    name: str
    jobs: list[ScheduledJob]


@dataclass(frozen=True)
class JobPlan:
    groups: list[JobGroup]

    @property
    def jobs(self) -> list[ScheduledJob]:
        return [job for group in self.groups for job in group.jobs]


@dataclass(frozen=True)
class SmartTrigger:
    signal_id: str
    topic: str
    reason: str
    action: str


SCHEDULE_GROUPS: list[JobGroup] = [
    JobGroup(
        name="high_frequency",
        jobs=[
            ScheduledJob("github_trending_check", "interval", minutes=15),
            ScheduledJob("hackathon_deadline_check", "interval", minutes=15),
            ScheduledJob("career_page_watcher", "interval", minutes=15),
            ScheduledJob("hn_frontpage_check", "interval", minutes=15),
        ],
    ),
    JobGroup(
        name="hourly",
        jobs=[
            ScheduledJob("reddit_collector", "interval", hours=1),
            ScheduledJob("bluesky_trends", "interval", hours=1),
            ScheduledJob("mastodon_trends", "interval", hours=1),
            ScheduledJob("devto_trending", "interval", hours=1),
            ScheduledJob("rss_all_feeds", "interval", hours=1),
            ScheduledJob("remoteok_jobs", "interval", hours=1),
        ],
    ),
    JobGroup(
        name="three_hourly",
        jobs=[
            ScheduledJob("github_search_exploding", "interval", hours=3),
            ScheduledJob("producthunt_launches", "interval", hours=3),
            ScheduledJob("pypi_npm_velocity", "interval", hours=3),
            ScheduledJob("google_trends_update", "interval", hours=3),
            ScheduledJob("devpost_scraper", "interval", hours=3),
            ScheduledJob("adzuna_fresh_jobs", "interval", hours=3),
        ],
    ),
    JobGroup(
        name="six_hourly",
        jobs=[
            ScheduledJob("cross_source_validation", "interval", hours=6),
            ScheduledJob("gap_finder_run", "interval", hours=6),
            ScheduledJob("sentiment_pipeline", "interval", hours=6),
            ScheduledJob("semantic_clustering", "interval", hours=6),
            ScheduledJob("score_update_all", "interval", hours=6),
            ScheduledJob("arxiv_paper_collector", "interval", hours=6),
            ScheduledJob("openalex_momentum", "interval", hours=6),
            ScheduledJob("crunchbase_funding", "interval", hours=6),
        ],
    ),
    JobGroup(
        name="daily",
        jobs=[
            ScheduledJob("daily_briefing_generate", "cron", hour=6),
            ScheduledJob("yc_companies_update", "cron", hour=6),
            ScheduledJob("wikipedia_pageviews", "cron", hour=6),
            ScheduledJob("sec_edgar_check", "cron", hour=6),
            ScheduledJob("skill_radar_update", "cron", hour=6),
            ScheduledJob("weekly_trend_report", "cron", hour=7, day_of_week="mon"),
            ScheduledJob("app_store_pain_mining", "cron", hour=2),
        ],
    ),
]


def collect_high_frequency() -> int:
    briefing = run_radar_once(use_live_network=False)
    return briefing.signals_24h


def build_job_plan() -> JobPlan:
    return JobPlan(groups=SCHEDULE_GROUPS)


def smart_triggers_for_signals(signals: list[SignalRecord], now: datetime | None = None) -> list[SmartTrigger]:
    now = now or datetime.now(UTC)
    triggers: list[SmartTrigger] = []
    recent_by_topic: dict[str, list[SignalRecord]] = defaultdict(list)

    for signal in signals:
        if signal.score > 90:
            triggers.append(_trigger(signal, "score_gt_90", "immediate_alert"))
        if signal.category == "hackathons" and _participant_growth(signal) >= 50:
            triggers.append(_trigger(signal, "hackathon_crowd_jump", "crowd_alert"))
        if signal.observed_at >= now - timedelta(hours=1):
            recent_by_topic[signal.topic.lower()].append(signal)

    for topic_signals in recent_by_topic.values():
        sources = {signal.source for signal in topic_signals}
        if len(sources) >= 3:
            triggers.append(_trigger(topic_signals[-1], "topic_hits_3_sources_1h", "deep_analysis"))

    return triggers


def _participant_growth(signal: SignalRecord) -> float:
    value = signal.metadata.get("participant_growth_pct", 0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _trigger(signal: SignalRecord, reason: str, action: str) -> SmartTrigger:
    return SmartTrigger(signal_id=str(signal.id), topic=signal.topic, reason=reason, action=action)
