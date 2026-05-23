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
    from internet_radar.collectors.app_stores.playstore_collector import Collector as GooglePlayCollector
    from internet_radar.collectors.code.crates_collector import Collector as CratesCollector
    from internet_radar.collectors.code.github_collector import Collector as GitHubCollector
    from internet_radar.collectors.code.libraries_io_collector import Collector as LibrariesIOCollector
    from internet_radar.collectors.finance.crunchbase_collector import Collector as CrunchbaseCollector
    from internet_radar.collectors.finance.yfinance_collector import Collector as YahooFinanceCollector
    from internet_radar.collectors.hackathons.leetcode_collector import Collector as LeetCodeCollector
    from internet_radar.collectors.hackathons.mlh_scraper import Collector as MLHCollector
    from internet_radar.collectors.jobs.adzuna_collector import Collector as AdzunaCollector
    from internet_radar.collectors.news.hashnode_collector import Collector as HashnodeCollector
    from internet_radar.collectors.news.producthunt_collector import Collector as ProductHuntCollector
    from internet_radar.collectors.news.rss_collector import Collector as RSSCollector
    from internet_radar.collectors.search.google_trends_collector import Collector as GoogleTrendsCollector
    from internet_radar.collectors.research.arxiv_collector import Collector as ArxivCollector
    from internet_radar.collectors.research.semantic_scholar import Collector as SemanticScholarCollector
    from internet_radar.collectors.search.brave_search_collector import Collector as BraveSearchCollector
    from internet_radar.collectors.search.tavily_collector import Collector as TavilyCollector
    from internet_radar.collectors.search.wayback_collector import Collector as WaybackCollector
    from internet_radar.collectors.social.bluesky_collector import Collector as BlueskyCollector
    from internet_radar.collectors.social.hackernews_search import Collector as HNSearchCollector
    from internet_radar.collectors.social.mastodon_collector import Collector as MastodonCollector

    samples = [
        GitHubCollector(use_live_network=False).collect()[0],
        CratesCollector(use_live_network=False).collect()[0],
        LibrariesIOCollector(use_live_network=False).collect()[0],
        HNSearchCollector(use_live_network=False).collect()[0],
        BlueskyCollector(use_live_network=False).collect()[0],
        MastodonCollector(use_live_network=False).collect()[0],
        ProductHuntCollector(use_live_network=False).collect()[0],
        RSSCollector(use_live_network=False).collect()[0],
        HashnodeCollector(use_live_network=False).collect()[0],
        AdzunaCollector(use_live_network=False).collect()[0],
        MLHCollector(use_live_network=False).collect()[0],
        LeetCodeCollector(use_live_network=False).collect()[0],
        ArxivCollector(use_live_network=False).collect()[0],
        SemanticScholarCollector(use_live_network=False).collect()[0],
        CrunchbaseCollector(use_live_network=False).collect()[0],
        YahooFinanceCollector(use_live_network=False).collect()[0],
        BraveSearchCollector(use_live_network=False).collect()[0],
        TavilyCollector(use_live_network=False).collect()[0],
        WaybackCollector(use_live_network=False).collect()[0],
        GoogleTrendsCollector(use_live_network=False).collect()[0],
        AppStoreCollector(use_live_network=False).collect()[0],
        GooglePlayCollector(use_live_network=False).collect()[0],
    ]

    assert [sample.category for sample in samples] == [
        "code",
        "code",
        "code",
        "social",
        "social",
        "social",
        "news",
        "news",
        "news",
        "jobs",
        "hackathons",
        "hackathons",
        "research",
        "research",
        "finance",
        "finance",
        "search",
        "search",
        "search",
        "search",
        "app_stores",
        "app_stores",
    ]
    assert {sample.source for sample in samples} >= {
        "GitHub Search",
        "crates.io",
        "Libraries.io",
        "Hacker News",
        "Bluesky",
        "Mastodon",
        "Product Hunt",
        "Tech RSS",
        "Hashnode",
        "Adzuna",
        "MLH",
        "LeetCode Contests",
        "arXiv",
        "Semantic Scholar",
        "Crunchbase",
        "Yahoo Finance",
        "Brave Search",
        "Tavily",
        "Wayback Machine",
        "Google Trends",
        "iTunes App Store",
        "Google Play",
    }
