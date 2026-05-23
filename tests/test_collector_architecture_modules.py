from __future__ import annotations

import importlib
from pathlib import Path


EXPECTED_COLLECTORS = {
    "code": [
        "github_collector",
        "github_trending_scraper",
        "pypi_collector",
        "npm_collector",
        "crates_collector",
        "libraries_io_collector",
    ],
    "social": [
        "reddit_collector",
        "hackernews_collector",
        "hackernews_search",
        "bluesky_collector",
        "mastodon_collector",
        "nitter_collector",
        "discord_monitor",
    ],
    "news": [
        "rss_collector",
        "devto_collector",
        "hashnode_collector",
        "lobsters_collector",
        "producthunt_collector",
        "tldr_collector",
    ],
    "jobs": [
        "remoteok_collector",
        "adzuna_collector",
        "themuse_collector",
        "arbeitnow_collector",
        "yc_jobs_scraper",
        "wellfound_scraper",
        "career_page_watcher",
    ],
    "hackathons": [
        "devpost_scraper",
        "unstop_scraper",
        "mlh_scraper",
        "hackerearth_collector",
        "codeforces_collector",
        "leetcode_collector",
    ],
    "research": [
        "arxiv_collector",
        "openalex_collector",
        "semantic_scholar",
        "wikipedia_collector",
        "paperswithcode_collector",
    ],
    "finance": [
        "crunchbase_collector",
        "yc_companies_collector",
        "sec_edgar_collector",
        "yfinance_collector",
    ],
    "search": [
        "duckduckgo_collector",
        "brave_search_collector",
        "tavily_collector",
        "wayback_collector",
        "google_trends_collector",
    ],
    "app_stores": [
        "appstore_collector",
        "playstore_collector",
        "steam_collector",
    ],
}


def test_architecture_collector_files_exist_and_export_collector_class():
    missing: list[str] = []
    for package, modules in EXPECTED_COLLECTORS.items():
        for module_name in modules:
            path = Path("internet_radar/collectors") / package / f"{module_name}.py"
            if not path.exists():
                missing.append(str(path))
                continue
            module = importlib.import_module(f"internet_radar.collectors.{package}.{module_name}")
            collector_class = getattr(module, "Collector", None)
            assert collector_class is not None, f"{module.__name__} must export Collector"
            collector = collector_class()
            assert hasattr(collector, "collect")
            assert getattr(collector, "category") == package
    assert not missing


def test_architecture_collector_wrappers_reuse_live_or_safe_fallbacks():
    from internet_radar.collectors.app_stores.appstore_collector import Collector as AppStoreCollector
    from internet_radar.collectors.code.github_collector import Collector as GitHubCollector
    from internet_radar.collectors.finance.crunchbase_collector import Collector as CrunchbaseCollector
    from internet_radar.collectors.search.google_trends_collector import Collector as GoogleTrendsCollector
    from internet_radar.collectors.research.arxiv_collector import Collector as ArxivCollector
    from internet_radar.collectors.social.hackernews_search import Collector as HNSearchCollector

    samples = [
        GitHubCollector(use_live_network=False).collect()[0],
        HNSearchCollector(use_live_network=False).collect()[0],
        ArxivCollector(use_live_network=False).collect()[0],
        CrunchbaseCollector(use_live_network=False).collect()[0],
        GoogleTrendsCollector(use_live_network=False).collect()[0],
        AppStoreCollector(use_live_network=False).collect()[0],
    ]

    assert [sample.category for sample in samples] == ["code", "social", "research", "finance", "search", "app_stores"]
    assert {sample.source for sample in samples} >= {
        "GitHub Search",
        "Hacker News",
        "arXiv",
        "Crunchbase",
        "Google Trends",
        "iTunes App Store",
    }
