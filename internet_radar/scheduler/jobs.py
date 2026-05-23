from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from internet_radar.alerts.alert_manager import build_alerts
from internet_radar.alerts.dispatcher import AlertDispatchResult, dispatch_alert
from internet_radar.collectors.live import (
    AdzunaCollector,
    ArbeitnowCollector,
    ArxivCollector,
    BlueskyCollector,
    CodeforcesCollector,
    CratesIOCollector,
    CrunchbaseCollector,
    DevToCollector,
    DevpostCollector,
    GooglePlayCollector,
    GoogleTrendsCollector,
    GitHubSearchCollector,
    GitHubTrendingCollector,
    HNAlgoliaCollector,
    HackerNewsCollector,
    ITunesCollector,
    LeetCodeContestsCollector,
    MLHCollector,
    MastodonCollector,
    NPMRegistryCollector,
    OpenAlexCollector,
    OpenCollectiveCollector,
    PackageCollector,
    ProductHuntCollector,
    PyPICollector,
    RSSCollector,
    RedditJSONCollector,
    RemoteOKCollector,
    SECEdgarCollector,
    SteamCollector,
    TheMuseCollector,
    WikipediaPageviewsCollector,
    YCCompaniesCollector,
    YCJobsCollector,
    default_collectors,
)
from internet_radar.config.settings import load_user_profile
from internet_radar.pipeline import run_radar_once
from internet_radar.storage.models import BriefingPayload
from internet_radar.storage.models import SignalRecord

CollectorFactory = Callable[[], object]


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


@dataclass(frozen=True)
class JobRunResult:
    job_name: str
    active_sources: int
    signals_24h: int
    source_health: dict[str, str]
    alert_dispatches: list[AlertDispatchResult]


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

JOB_COLLECTOR_FACTORIES: dict[str, list[CollectorFactory]] = {
    "github_trending_check": [GitHubTrendingCollector],
    "hackathon_deadline_check": [DevpostCollector, MLHCollector, CodeforcesCollector, LeetCodeContestsCollector],
    "career_page_watcher": [YCJobsCollector, RemoteOKCollector, TheMuseCollector, ArbeitnowCollector],
    "hn_frontpage_check": [HackerNewsCollector, HNAlgoliaCollector],
    "reddit_collector": [RedditJSONCollector],
    "bluesky_trends": [BlueskyCollector],
    "mastodon_trends": [MastodonCollector],
    "devto_trending": [DevToCollector],
    "rss_all_feeds": [RSSCollector],
    "remoteok_jobs": [RemoteOKCollector],
    "github_search_exploding": [GitHubSearchCollector, GitHubTrendingCollector],
    "producthunt_launches": [ProductHuntCollector],
    "pypi_npm_velocity": [PyPICollector, NPMRegistryCollector, CratesIOCollector, PackageCollector],
    "google_trends_update": [GoogleTrendsCollector],
    "devpost_scraper": [DevpostCollector],
    "adzuna_fresh_jobs": [AdzunaCollector],
    "arxiv_paper_collector": [ArxivCollector],
    "openalex_momentum": [OpenAlexCollector],
    "crunchbase_funding": [CrunchbaseCollector, OpenCollectiveCollector],
    "yc_companies_update": [YCCompaniesCollector],
    "wikipedia_pageviews": [WikipediaPageviewsCollector],
    "sec_edgar_check": [SECEdgarCollector],
    "skill_radar_update": [RemoteOKCollector, PyPICollector, NPMRegistryCollector, ArxivCollector],
    "app_store_pain_mining": [ITunesCollector, GooglePlayCollector, SteamCollector],
}


def collect_high_frequency() -> int:
    briefing = run_radar_once(use_live_network=False)
    return briefing.signals_24h


def collectors_for_job(job_name: str, use_live_network: bool = True) -> list[object]:
    factories = JOB_COLLECTOR_FACTORIES.get(job_name)
    if not factories:
        return default_collectors(use_live_network=use_live_network)
    if not use_live_network:
        return default_collectors(use_live_network=False)
    return [factory() for factory in factories]


def run_scheduled_job(
    job_name: str,
    *,
    db_path: str | Path | None = None,
    use_live_network: bool | None = None,
    dispatch_alerts: bool | None = None,
) -> JobRunResult:
    if use_live_network is None:
        use_live_network = os.getenv("INTERNET_RADAR_USE_LIVE", "0") == "1"
    briefing = run_radar_once(
        collectors=collectors_for_job(job_name, use_live_network=use_live_network),
        db_path=db_path,
        use_live_network=use_live_network,
    )
    return JobRunResult(
        job_name=job_name,
        active_sources=briefing.active_sources,
        signals_24h=briefing.signals_24h,
        source_health=briefing.source_health,
        alert_dispatches=_maybe_dispatch_alerts(briefing, dispatch_alerts=dispatch_alerts),
    )


def build_job_plan() -> JobPlan:
    return JobPlan(groups=SCHEDULE_GROUPS)


def _maybe_dispatch_alerts(briefing: BriefingPayload, dispatch_alerts: bool | None) -> list[AlertDispatchResult]:
    if dispatch_alerts is None:
        dispatch_alerts = os.getenv("INTERNET_RADAR_DISPATCH_ALERTS", "0") == "1"
    if not dispatch_alerts:
        return []
    profile = load_user_profile()
    results: list[AlertDispatchResult] = []
    for alert in build_alerts(briefing.top_signals, profile):
        results.extend(dispatch_alert(alert))
    return results


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
