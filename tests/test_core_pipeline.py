from __future__ import annotations

from datetime import UTC, datetime, timedelta


def test_source_registry_has_architecture_coverage():
    from internet_radar.sources.registry import SOURCE_REGISTRY, enabled_sources

    assert len(SOURCE_REGISTRY) >= 64
    categories = {source.category for source in SOURCE_REGISTRY}
    assert {"code", "social", "news", "jobs", "research", "finance", "search", "app_stores"} <= categories

    live_names = {source.name for source in enabled_sources()}
    assert {"GitHub Search", "Reddit JSON", "Hacker News", "Dev.to", "RemoteOK", "arXiv"} <= live_names


def test_storage_upserts_signals(tmp_path):
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.models import SignalRecord

    db_path = tmp_path / "radar.sqlite"
    store = RadarStore(db_path)
    signal = SignalRecord(
        id="github:test",
        topic="browser agents",
        title="Browser agents are growing",
        source="GitHub Search",
        category="code",
        url="https://example.com/repo",
        score=72,
        velocity=19,
        observed_at=datetime.now(UTC),
    )

    store.upsert_signals([signal, signal])
    stored = store.list_signals(limit=10)

    assert len(stored) == 1
    assert stored[0].topic == "browser agents"
    assert stored[0].score == 72


def test_cross_source_validator_classifies_confirmed_trend():
    from internet_radar.signals.cross_source_validator import CrossSourceValidator

    result = CrossSourceValidator().validate(
        "local llm agents",
        {
            "github_star_spike": {"detected": True, "first_seen": "2026-05-20T00:00:00Z"},
            "reddit_discussion": {"detected": True, "first_seen": "2026-05-21T00:00:00Z"},
            "hn_front_page": {"detected": True, "first_seen": "2026-05-22T00:00:00Z"},
            "arxiv_paper_velocity": {"detected": True, "first_seen": "2026-05-23T00:00:00Z"},
            "job_postings_rising": {"detected": True, "first_seen": "2026-05-23T01:00:00Z"},
        },
    )

    assert result.phase == "CONFIRMED EMERGING TREND"
    assert result.confidence >= 80
    assert result.earliest_signal == "github_star_spike"


def test_deduplicator_prefers_highest_score():
    from internet_radar.signals.deduplicator import deduplicate_signals
    from internet_radar.storage.models import SignalRecord

    older = datetime.now(UTC) - timedelta(hours=1)
    records = [
        SignalRecord(id="a", topic="MCP", title="MCP is hot", source="HN", category="social", score=50, observed_at=older),
        SignalRecord(id="b", topic="mcp", title="MCP is hot", source="GitHub", category="code", score=83),
    ]

    deduped = deduplicate_signals(records)

    assert len(deduped) == 1
    assert deduped[0].id == "b"


def test_master_scorer_bounds_and_timing():
    from internet_radar.scoring.master_scorer import MasterScorer

    scorer = MasterScorer()

    trend_score = scorer.score_trend(
        {
            "velocity_score": 40,
            "confirming_sources": 6,
            "phase": "EMERGING",
            "funding_detected": True,
        }
    )
    internship_score = scorer.score_internship(
        {
            "posted_hours_ago": 4,
            "applicant_ratio": 0.1,
            "description": "python ai streamlit",
            "company_growth": 0.8,
        },
        {"skills": ["python", "ai"]},
    )

    assert 0 <= trend_score <= 100
    assert trend_score == 100
    assert internship_score > 70


def test_ollama_router_uses_installed_model_and_deterministic_fallback():
    from internet_radar.brain.llm_router import LLMRouter

    router = LLMRouter(available_models=["qwen2.5:0.5b"])

    assert router.route("classify", content_length=80).model == "qwen2.5:0.5b"
    fallback = router.classify_signal("Browser agents and local LLM tools are exploding", allow_network=False)

    assert fallback["topic"] == "browser agents"
    assert fallback["sentiment"] in {"positive", "neutral", "negative"}
    assert 0 <= fallback["confidence"] <= 100


def test_ollama_router_normalizes_model_json():
    from internet_radar.brain.llm_router import LLMRouter

    class FakeOllama:
        def available_models(self):
            return ["qwen2.5:0.5b"]

        def generate_json(self, prompt):
            return {"topic": "Browser Agents", "sentiment": "", "confidence": "0.95"}

    router = LLMRouter(ollama_client=FakeOllama())
    result = router.classify_signal("browser agents exploding", allow_network=True)

    assert result == {"topic": "browser agents", "sentiment": "positive", "confidence": 95}


def test_ollama_router_keeps_obvious_deterministic_topic():
    from internet_radar.brain.llm_router import LLMRouter

    class FakeOllama:
        def available_models(self):
            return ["qwen2.5:0.5b"]

        def generate_json(self, prompt):
            return {"topic": "web security", "sentiment": "positive", "confidence": 88}

    router = LLMRouter(ollama_client=FakeOllama())
    result = router.classify_signal("browser agents exploding with local llm", allow_network=True)

    assert result["topic"] == "browser agents"
    assert result["sentiment"] == "positive"


def test_ollama_router_keeps_obvious_deterministic_sentiment():
    from internet_radar.brain.llm_router import LLMRouter

    class FakeOllama:
        def available_models(self):
            return ["qwen2.5:0.5b"]

        def generate_json(self, prompt):
            return {"topic": "browser agents", "sentiment": "negative", "confidence": 88}

    router = LLMRouter(ollama_client=FakeOllama())
    result = router.classify_signal("browser agents exploding fast", allow_network=True)

    assert result["sentiment"] == "positive"


def test_pipeline_runs_with_fake_collectors_and_persists(tmp_path):
    from internet_radar.pipeline import run_radar_once
    from internet_radar.storage.db import RadarStore
    from internet_radar.storage.models import SignalRecord

    class FakeCollector:
        name = "Fake Collector"
        category = "code"

        def collect(self):
            return [
                SignalRecord(
                    id="fake:1",
                    topic="browser agents",
                    title="Browser agents are exploding",
                    source=self.name,
                    category=self.category,
                    score=60,
                    velocity=12,
                )
            ]

    db_path = tmp_path / "radar.sqlite"
    result = run_radar_once(collectors=[FakeCollector()], db_path=db_path, use_live_network=False)

    assert result.active_sources == 1
    assert result.signals_24h == 1
    assert result.top_signals[0].topic == "browser agents"
    assert result.collection_mode == "sample"
    assert result.collection_duration_seconds >= 0
    assert result.source_counts["Fake Collector"] == 1
    assert "Fake Collector" in result.source_durations_seconds
    assert RadarStore(db_path).list_signals()[0].source == "Fake Collector"


def test_pipeline_keeps_running_when_one_collector_fails(tmp_path):
    from internet_radar.pipeline import run_radar_once
    from internet_radar.storage.models import SignalRecord

    class GoodCollector:
        name = "Good Collector"
        category = "code"

        def collect(self):
            return [
                SignalRecord(
                    id="good:1",
                    topic="browser agents",
                    title="Browser agents are growing",
                    source=self.name,
                    category=self.category,
                    score=72,
                )
            ]

    class BadCollector:
        name = "Bad Collector"
        category = "social"

        def collect(self):
            raise RuntimeError("source down")

    result = run_radar_once(
        collectors=[GoodCollector(), BadCollector()],
        db_path=tmp_path / "radar.sqlite",
        use_live_network=False,
    )

    assert result.signals_24h == 1
    assert result.source_health["Good Collector"] == "live (1)"
    assert result.source_health["Bad Collector"] == "error: source down"


def test_pipeline_keeps_lower_scored_category_signals_for_dashboard_tabs(tmp_path):
    from internet_radar.pipeline import run_radar_once
    from internet_radar.storage.models import SignalRecord

    class CrowdedCodeCollector:
        name = "Crowded Code"
        category = "code"

        def collect(self):
            return [
                SignalRecord(
                    id=f"code:{index}",
                    topic=f"code topic {index}",
                    title=f"Code signal {index}",
                    source=self.name,
                    category=self.category,
                    score=100,
                )
                for index in range(120)
            ]

    class HackathonCollector:
        name = "Hackathon Source"
        category = "hackathons"

        def collect(self):
            return [
                SignalRecord(
                    id="hackathon:1",
                    topic="ai hackathon",
                    title="AI hackathon",
                    source=self.name,
                    category=self.category,
                    score=65,
                )
            ]

    result = run_radar_once(
        collectors=[CrowdedCodeCollector(), HackathonCollector()],
        db_path=tmp_path / "radar.sqlite",
        use_live_network=False,
    )

    assert any(signal.category == "hackathons" for signal in result.top_signals)


def test_sample_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_arxiv_feed,
        parse_devto_articles,
        parse_hackernews_items,
        parse_remoteok_jobs,
    )

    hn = parse_hackernews_items(
        [
            {
                "id": 1,
                "title": "Show HN: Local AI browser agent",
                "url": "https://example.com",
                "score": 231,
                "descendants": 42,
            }
        ]
    )
    devto = parse_devto_articles(
        [
            {
                "id": 2,
                "title": "Building with Ollama and Streamlit",
                "url": "https://dev.to/example",
                "tag_list": ["ai", "python"],
                "public_reactions_count": 20,
            }
        ]
    )
    remoteok = parse_remoteok_jobs(
        [
            {"legal": "metadata"},
            {
                "id": "job-1",
                "position": "AI Intern",
                "company": "Signal Labs",
                "url": "https://remoteok.com/job",
                "tags": ["Python", "AI"],
            },
        ]
    )
    arxiv = parse_arxiv_feed(
        """<?xml version="1.0"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2605.00001</id>
            <title>Agentic Browser Automation</title>
            <summary>Local LLM agents for browser automation.</summary>
          </entry>
        </feed>
        """
    )

    assert hn[0].topic == "local ai browser agent"
    assert devto[0].category == "news"
    assert remoteok[0].category == "jobs"
    assert arxiv[0].source == "arXiv"


def test_second_wave_no_key_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_arbeitnow_jobs,
        parse_codeforces_contests,
        parse_coingecko_trending,
        parse_itunes_results,
        parse_lobsters_stories,
        parse_npm_package,
        parse_openalex_works,
        parse_pypi_package,
        parse_steam_featured,
        parse_themuse_jobs,
        parse_wikipedia_pageviews,
    )

    assert parse_lobsters_stories(
        [{"short_id": "abc", "title": "Local LLM agents", "url": "https://lobste.rs/s/abc", "score": 42, "comments_count": 9}]
    )[0].source == "Lobsters"

    assert parse_themuse_jobs(
        {
            "results": [
                {
                    "id": 123,
                    "name": "AI Platform Intern",
                    "company": {"name": "Muse Labs"},
                    "refs": {"landing_page": "https://themuse.com/jobs/123"},
                    "categories": [{"name": "Engineering"}],
                }
            ]
        }
    )[0].title == "AI Platform Intern at Muse Labs"

    assert parse_arbeitnow_jobs(
        {
            "data": [
                {
                    "slug": "python-ai-engineer",
                    "title": "Python AI Engineer",
                    "company_name": "Arbeitnow Labs",
                    "url": "https://arbeitnow.com/jobs/python-ai-engineer",
                    "tags": ["Python", "AI"],
                }
            ]
        }
    )[0].category == "jobs"

    assert parse_codeforces_contests(
        {"result": [{"id": 10, "name": "Codeforces Round AI", "phase": "BEFORE", "relativeTimeSeconds": -3600}]}
    )[0].category == "hackathons"

    assert parse_openalex_works(
        {
            "results": [
                {
                    "id": "https://openalex.org/W1",
                    "display_name": "Agentic Browser Automation",
                    "cited_by_count": 34,
                    "authorships": [{"institutions": [{"display_name": "MIT"}]}],
                }
            ]
        }
    )[0].metadata["citations"] == 34

    assert parse_wikipedia_pageviews(
        {"items": [{"article": "Large_language_model", "views": 1200}, {"article": "Large_language_model", "views": 1300}]}
    )[0].velocity == 2500

    assert parse_coingecko_trending(
        {"coins": [{"item": {"id": "bittensor", "name": "Bittensor", "symbol": "TAO", "score": 2}}]}
    )[0].category == "finance"

    assert parse_itunes_results(
        {"results": [{"trackId": 99, "trackName": "AI Assistant", "averageUserRating": 2.1, "trackViewUrl": "https://apps.apple.com/app/99"}]}
    )[0].topic == "ai assistant"

    assert parse_steam_featured(
        {"large_capsules": [{"id": 1, "name": "Automation Simulator", "discount_percent": 25, "header_image": "https://cdn.example/game.jpg"}]}
    )[0].source == "Steam"

    assert parse_pypi_package("streamlit", {"info": {"summary": "Build data apps fast", "package_url": "https://pypi.org/project/streamlit/"}})[
        0
    ].source == "PyPI"

    assert parse_npm_package(
        "ollama", {"description": "Ollama JavaScript client", "homepage": "https://www.npmjs.com/package/ollama"}
    )[0].source == "npm Registry"


def test_default_live_collectors_include_no_key_second_wave():
    from internet_radar.collectors.live import default_collectors

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert {
        "Lobsters",
        "The Muse",
        "Arbeitnow",
        "Codeforces",
        "OpenAlex",
        "Wikipedia Pageviews",
        "CoinGecko",
        "iTunes App Store",
        "Steam",
        "Special Intelligence",
    } <= names


def test_third_wave_no_key_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_duckduckgo_results,
        parse_google_trends_rss,
        parse_paperswithcode_results,
        parse_sec_submissions,
        parse_yc_companies,
    )

    assert parse_yc_companies(
        [
            {
                "id": 1,
                "name": "AgentOps",
                "one_liner": "Observability for AI browser agents",
                "batch": "W26",
                "industries": ["Developer Tools", "AI"],
                "url": "https://www.ycombinator.com/companies/agentops",
            }
        ]
    )[0].source == "YC Companies"

    assert parse_sec_submissions(
        {
            "name": "NVIDIA CORP",
            "cik": "0001045810",
            "filings": {"recent": {"form": ["10-K", "8-K"], "accessionNumber": ["0001", "0002"], "filingDate": ["2026-03-01", "2026-05-01"]}},
        }
    )[0].metadata["form"] == "10-K"

    assert parse_duckduckgo_results(
        """
        <a class="result__a" href="https://example.com/agents">Browser agents trend report</a>
        <a class="result__snippet">Teams complain debugging browser automation is painful.</a>
        """
    )[0].source == "DuckDuckGo"

    google_trend = parse_google_trends_rss(
        """<?xml version="1.0"?>
        <rss xmlns:ht="https://trends.google.com/trends/trendingsearches/daily">
          <channel>
            <item>
              <title>browser agents</title>
              <link>https://trends.google.com/trends/explore?q=browser%20agents</link>
              <ht:approx_traffic>200K+</ht:approx_traffic>
              <ht:news_item>
                <ht:news_item_title>Browser automation tools keep rising</ht:news_item_title>
                <ht:news_item_url>https://example.com/browser-agents</ht:news_item_url>
              </ht:news_item>
            </item>
          </channel>
        </rss>
        """
    )[0]

    assert google_trend.source == "Google Trends"
    assert google_trend.velocity == 200_000

    assert parse_paperswithcode_results(
        {
            "results": [
                {
                    "id": "pwc-1",
                    "title": "Agentic Browser Automation",
                    "abstract": "Code and benchmarks for local browser agents.",
                    "url_abs": "https://paperswithcode.com/paper/agentic-browser-automation",
                    "repositories": [{"stars": 321}],
                }
            ]
        }
    )[0].metadata["repo_stars"] == 321


def test_default_live_collectors_include_no_key_third_wave():
    from internet_radar.collectors.live import default_collectors

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert {
        "DuckDuckGo",
        "Google Trends",
        "YC Companies",
        "SEC EDGAR",
        "Papers With Code",
    } <= names


def test_fourth_wave_no_key_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_bluesky_posts,
        parse_crates_results,
        parse_hashnode_posts,
        parse_leetcode_contests,
        parse_mastodon_statuses,
        parse_mlh_events_html,
        parse_playstore_search_html,
        parse_rss_entries,
        parse_wayback_available,
        parse_yahoo_quote,
    )

    assert parse_crates_results(
        {"crates": [{"id": "tokio", "name": "tokio", "description": "Async runtime", "downloads": 50000000, "recent_downloads": 1200000}]}
    )[0].source == "crates.io"

    assert parse_bluesky_posts(
        {"posts": [{"uri": "at://did/post/1", "record": {"text": "Browser agents are moving fast"}, "author": {"handle": "builder.dev"}, "likeCount": 10, "replyCount": 2, "repostCount": 3}]}
    )[0].category == "social"

    assert parse_mastodon_statuses(
        [{"id": "1", "content": "<p>Local LLM browser automation trend</p>", "url": "https://mastodon.example/@dev/1", "favourites_count": 8}]
    )[0].source == "Mastodon"

    assert parse_rss_entries(
        """
        <rss>
          <channel>
            <title>Feed title</title>
            <link>https://example.com/feed</link>
            <description>Feed description</description>
            <item>
              <title><![CDATA[Agentic browser automation weekly]]></title>
              <link>https://example.com/agentic-browser-automation</link>
              <description><![CDATA[<p>Local LLM workflows are accelerating.</p>]]></description>
            </item>
          </channel>
        </rss>
        """,
        source_name="OpenAI Blog",
    )[0].source == "OpenAI Blog"

    assert parse_hashnode_posts(
        {
            "data": {
                "storiesFeed": {
                    "edges": [
                        {
                            "node": {
                                "id": "hash-1",
                                "title": "Building AI agents",
                                "brief": "Practical notes.",
                                "url": "https://hashnode.example/agents",
                                "reactionCount": 12,
                                "responseCount": 3,
                                "tags": [{"name": "AI"}],
                            }
                        }
                    ]
                }
            }
        }
    )[0].source == "Hashnode"

    assert parse_mlh_events_html('<a href="/events/local-ai-hack" class="event event-link"><h3>Local AI Hackathon</h3></a>')[
        0
    ].category == "hackathons"

    assert parse_leetcode_contests({"data": {"allContests": [{"title": "Weekly Contest 500", "titleSlug": "weekly-contest-500", "startTime": 1770000000, "duration": 5400}]}})[
        0
    ].source == "LeetCode Contests"

    assert parse_yahoo_quote(
        {"quoteResponse": {"result": [{"symbol": "NVDA", "longName": "NVIDIA Corporation", "regularMarketPrice": 110.5, "regularMarketChangePercent": 2.7}]}}
    )[0].category == "finance"

    assert parse_wayback_available(
        {"archived_snapshots": {"closest": {"available": True, "status": "200", "timestamp": "20260523000000", "url": "https://web.archive.org/snapshot"}}},
        "https://openai.com",
    )[0].source == "Wayback Machine"

    assert parse_playstore_search_html('<a href="/store/apps/details?id=com.example.agent">AI Agent Reviews</a>')[0].source == "Google Play"


def test_default_live_collectors_include_no_key_fourth_wave():
    from internet_radar.collectors.live import default_collectors

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert {
        "crates.io",
        "Bluesky",
        "Mastodon",
        "Tech RSS",
        "Hashnode",
        "MLH",
        "LeetCode Contests",
        "Yahoo Finance",
        "Wayback Machine",
        "Google Play",
    } <= names


def test_source_specific_fallback_preserves_real_collector_identity(monkeypatch):
    from internet_radar.collectors.live import GooglePlayCollector

    collector = GooglePlayCollector()

    def fail_get_text(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(collector, "get_text", fail_get_text)

    signal = collector.collect()[0]

    assert signal.source == "Google Play"
    assert signal.category == "app_stores"
    assert signal.metadata["fallback"] is True


def test_registry_parity_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_devpost_hackathons_html,
        parse_github_trending_html,
        parse_gitlab_projects,
        parse_hn_algolia_hits,
        parse_huggingface_models,
        parse_mcp_servers_markdown,
        parse_opencollective_search,
        parse_stackoverflow_questions,
        parse_tldr_html,
        parse_yc_jobs_html,
    )

    assert parse_github_trending_html('<h2><a href="/openai/codex"> openai / codex </a></h2>')[0].source == "GitHub Trending"

    assert parse_hn_algolia_hits(
        [{"objectID": "1", "title": "Browser agents on Hacker News", "url": "https://example.com", "points": 42, "num_comments": 9}]
    )[0].source == "HN Algolia"

    assert parse_tldr_html('<a href="/tech/2026-05-23">Browser agents briefing</a>')[0].source == "TLDR Newsletter"

    assert parse_yc_jobs_html('<a href="/companies/acme/jobs/ai-intern">AI Intern at Acme</a>')[0].source == "YC Jobs"

    assert parse_devpost_hackathons_html('<a href="/hackathons/local-ai">Local AI Hackathon</a>')[0].category == "hackathons"

    assert parse_stackoverflow_questions(
        {"items": [{"question_id": 1, "title": "How to run local LLM agents?", "score": 5, "answer_count": 2, "tags": ["python", "llm"], "link": "https://stackoverflow.com/q/1"}]}
    )[0].source == "Stack Overflow"

    assert parse_huggingface_models(
        [{"modelId": "openai/example-agent", "downloads": 12000, "likes": 300, "tags": ["agents", "text-generation"]}]
    )[0].source == "Hugging Face Models"

    assert parse_gitlab_projects(
        [{"id": 1, "path_with_namespace": "group/agent-kit", "web_url": "https://gitlab.com/group/agent-kit", "star_count": 80}]
    )[0].source == "GitLab Explore"

    assert parse_opencollective_search(
        {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "id": "oc-1",
                            "slug": "agent-tools",
                            "name": "Agent Tools",
                            "type": "COLLECTIVE",
                            "description": "Open source agent tooling.",
                            "stats": {"totalAmountReceived": {"value": 25000}},
                        }
                    ]
                }
            }
        }
    )[0].source == "OpenCollective"

    assert parse_mcp_servers_markdown("- [Filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)")[0].source == "MCP Servers Directory"


def test_default_live_collectors_cover_enabled_registry_sources():
    from internet_radar.collectors.live import default_collectors
    from internet_radar.sources.registry import enabled_sources

    live_names = {collector.name for collector in default_collectors(use_live_network=True)}
    enabled_names = {source.name for source in enabled_sources()}

    assert enabled_names <= live_names


def test_new_free_sources_are_enabled_by_default():
    from internet_radar.collectors.live import default_collectors
    from internet_radar.sources.registry import enabled_sources

    expected = {
        "Crossref",
        "Europe PMC",
        "PubMed",
        "bioRxiv",
        "medRxiv",
        "GDELT",
        "Common Crawl",
        "Greenhouse Jobs",
        "Lever Jobs",
        "Grants.gov",
        "USAspending",
        "Docker Hub",
        "RubyGems",
        "F-Droid",
    }
    enabled_names = {source.name for source in enabled_sources()}
    collector_names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert expected <= enabled_names
    assert expected <= collector_names


def test_google_trends_collector_uses_source_specific_fallback(monkeypatch):
    from internet_radar.collectors.live import GoogleTrendsCollector

    collector = GoogleTrendsCollector()

    def fail_get_text(*args, **kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr(collector, "get_text", fail_get_text)

    signal = collector.collect()[0]

    assert signal.source == "Google Trends"
    assert signal.category == "search"
    assert signal.metadata["approx_traffic"] == 50_000


def test_keyed_architecture_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_adzuna_jobs,
        parse_brave_search_results,
        parse_crunchbase_funding,
        parse_hackerearth_challenges,
        parse_libraries_io_project,
        parse_producthunt_posts,
        parse_semantic_scholar_papers,
        parse_tavily_results,
    )

    assert parse_libraries_io_project(
        "streamlit",
        {
            "name": "streamlit",
            "platform": "pypi",
            "description": "Build data apps",
            "dependent_repos_count": 1200,
            "stars": 36000,
            "repository_url": "https://github.com/streamlit/streamlit",
        },
    )[0].source == "Libraries.io"

    assert parse_producthunt_posts(
        {
            "data": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                "id": "ph-1",
                                "name": "Agent Browser",
                                "tagline": "Automate browser workflows",
                                "votesCount": 420,
                                "commentsCount": 38,
                                "url": "https://producthunt.com/posts/agent-browser",
                                "topics": {"edges": [{"node": {"name": "Artificial Intelligence"}}]},
                            }
                        }
                    ]
                }
            }
        }
    )[0].source == "Product Hunt"

    assert parse_adzuna_jobs(
        {
            "results": [
                {
                    "id": "adz-1",
                    "title": "Machine Learning Intern",
                    "company": {"display_name": "Signal Labs"},
                    "location": {"display_name": "Remote"},
                    "redirect_url": "https://adzuna.example/job",
                    "created": "2026-05-23T00:00:00Z",
                }
            ]
        }
    )[0].category == "jobs"

    assert parse_hackerearth_challenges(
        {"challenges": [{"id": "he-1", "title": "AI Agent Hackathon", "participants": 345, "url": "https://hackerearth.example/challenge"}]}
    )[0].source == "HackerEarth"

    assert parse_semantic_scholar_papers(
        {"data": [{"paperId": "paper-1", "title": "Agentic Browser Automation", "citationCount": 42, "year": 2026, "url": "https://semanticscholar.org/paper/1"}]}
    )[0].metadata["citations"] == 42

    assert parse_crunchbase_funding(
        {
            "entities": [
                {
                    "uuid": "round-1",
                    "properties": {
                        "funded_organization_identifier": {"value": "AgentOps"},
                        "money_raised": {"value": 7_000_000},
                        "investment_type": "seed",
                        "announced_on": "2026-05-20",
                    },
                }
            ]
        }
    )[0].metadata["amount"] == 7_000_000

    assert parse_brave_search_results(
        {"web": {"results": [{"title": "Browser agents pain report", "url": "https://example.com", "description": "Debugging agents is painful."}]}}
    )[0].source == "Brave Search"

    assert parse_tavily_results(
        {"answer": "Browser agents are rising.", "results": [{"title": "Browser agents report", "url": "https://example.com", "content": "Browser agents keep rising.", "score": 0.8}]}
    )[0].score == 90


def test_new_free_collectors_parse_representative_payloads():
    from internet_radar.collectors.live import (
        parse_biorxiv_papers,
        parse_common_crawl_results,
        parse_crossref_works,
        parse_dockerhub_repositories,
        parse_europepmc_results,
        parse_fdroid_index,
        parse_gdelt_articles,
        parse_grantsgov_opportunities,
        parse_greenhouse_jobs,
        parse_lever_jobs,
        parse_pubmed_esearch,
        parse_rubygems_results,
        parse_usaspending_awards,
    )

    assert parse_crossref_works(
        {"message": {"items": [{"DOI": "10.123/agent", "title": ["Agent Browser Study"], "is-referenced-by-count": 42, "URL": "https://doi.org/10.123/agent"}]}}
    )[0].source == "Crossref"

    assert parse_europepmc_results(
        {"resultList": {"result": [{"id": "PMC1", "title": "Agentic automation in biomedicine", "citedByCount": 12, "journalTitle": "AI Journal"}]}}
    )[0].source == "Europe PMC"

    assert parse_pubmed_esearch({"esearchresult": {"idlist": ["123", "456"], "count": "18"}})[0].metadata["result_count"] == 18

    assert parse_biorxiv_papers(
        "bioRxiv",
        {"collection": [{"doi": "10.1101/agent", "title": "Agent systems preprint", "abstract": "A browser agent preprint.", "date": "2026-05-20"}]},
    )[0].source == "bioRxiv"

    assert parse_gdelt_articles(
        {"articles": [{"title": "AI agents reshape software", "url": "https://news.example/agents", "domain": "news.example", "seendate": "20260526T120000Z"}]}
    )[0].source == "GDELT"

    assert parse_common_crawl_results(
        [{"url": "https://example.com/agents", "mime": "text/html", "timestamp": "20260526000000", "status": "200"}]
    )[0].source == "Common Crawl"

    assert parse_greenhouse_jobs(
        {"jobs": [{"id": 1, "title": "AI Intern", "absolute_url": "https://boards.greenhouse.io/example/jobs/1", "location": {"name": "Remote"}}]},
        board="example",
    )[0].source == "Greenhouse Jobs"

    assert parse_lever_jobs(
        [{"id": "job-1", "text": "AI Platform Intern", "hostedUrl": "https://jobs.lever.co/example/job-1", "categories": {"location": "Remote"}}],
        company="example",
    )[0].source == "Lever Jobs"

    assert parse_grantsgov_opportunities(
        {"oppHits": [{"id": "opp-1", "title": "AI Research Grant", "agency": "NSF", "openDate": "2026-05-01"}]}
    )[0].source == "Grants.gov"

    assert parse_usaspending_awards(
        {"results": [{"Award ID": "FAIN-1", "Recipient Name": "Agent Labs", "Award Amount": 1200000, "Awarding Agency": "NSF"}]}
    )[0].metadata["amount"] == 1200000

    assert parse_dockerhub_repositories(
        {"results": [{"name": "agent-runtime", "namespace": "example", "pull_count": 12345, "star_count": 90, "description": "Browser agent runtime"}]}
    )[0].source == "Docker Hub"

    assert parse_rubygems_results(
        [{"name": "agentic", "info": "Agent workflow gem", "downloads": 1234, "project_uri": "https://rubygems.org/gems/agentic"}]
    )[0].source == "RubyGems"

    assert parse_fdroid_index(
        {"packages": {"org.example.agent": {"metadata": {"name": {"en-US": "Agent App"}, "summary": {"en-US": "Local AI assistant"}}, "versions": {}}}}
    )[0].source == "F-Droid"


def test_new_free_collectors_use_live_friendly_defaults():
    from internet_radar.collectors.live import CommonCrawlCollector, GreenhouseJobsCollector, LeverJobsCollector, USASpendingCollector

    assert GreenhouseJobsCollector().boards == ["databricks", "stripe"]
    assert LeverJobsCollector().companies == ["spotify", "coupa", "Onehouse", "arcadia"]

    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "results": [
                    {
                        "Award ID": "FAIN-1",
                        "Recipient Name": "Agent Labs",
                        "Award Amount": 1200000,
                        "Awarding Agency": "NSF",
                    }
                ]
            }

    def fake_post(url: str, **kwargs: object) -> Response:
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return Response()

    collector = USASpendingCollector(http_post=fake_post)
    collector.rate_limiter = None
    records = collector.collect()

    assert captured["url"] == "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    assert captured["json"] == {
        "filters": {"keywords": ["artificial intelligence"], "award_type_codes": ["A", "B", "C", "D"]},
        "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
        "page": 1,
        "limit": 10,
        "sort": "Award Amount",
        "order": "desc",
    }
    assert records[0].source == "USAspending"

    common_crawl_calls: list[tuple[str, dict[str, object]]] = []

    class CommonCrawlResponse:
        text = '{"url":"https://example.com/agents","timestamp":"20260526000000","status":"200"}'

        def __init__(self, payload: object | None = None) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> object:
            return self.payload

    def fake_get(url: str, **kwargs: object) -> CommonCrawlResponse:
        common_crawl_calls.append((url, kwargs))
        if url.endswith("collinfo.json"):
            return CommonCrawlResponse([{"id": "CC-MAIN-2026-21"}])
        return CommonCrawlResponse()

    common_crawl = CommonCrawlCollector(target="example.com/*")
    common_crawl.rate_limiter = None
    common_crawl.http_get = fake_get

    records = common_crawl.collect()

    assert common_crawl_calls[1][1]["params"] == {"url": "example.com/*", "output": "json", "limit": 10}
    assert records[0].source == "Common Crawl"


def test_keyed_collectors_are_added_to_live_defaults_when_credentials_exist(monkeypatch):
    from internet_radar.collectors.live import default_collectors

    monkeypatch.setenv("LIBRARIES_IO_API_KEY", "key")
    monkeypatch.setenv("PRODUCTHUNT_TOKEN", "key")
    monkeypatch.setenv("ADZUNA_APP_ID", "app")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    monkeypatch.setenv("HACKEREARTH_API_KEY", "key")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "key")
    monkeypatch.setenv("CRUNCHBASE_API_KEY", "key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "key")
    monkeypatch.setenv("TAVILY_API_KEY", "key")

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert {
        "Libraries.io",
        "Product Hunt",
        "Adzuna",
        "HackerEarth",
        "Semantic Scholar",
        "Crunchbase",
        "Brave Search",
        "Tavily",
    } <= names


def test_free_only_mode_skips_paid_keyed_collectors(monkeypatch):
    from internet_radar.collectors.live import default_collectors

    monkeypatch.setenv("INTERNET_RADAR_FREE_ONLY", "1")
    monkeypatch.setenv("CRUNCHBASE_API_KEY", "key")
    monkeypatch.setenv("BRAVE_SEARCH_API_KEY", "key")
    monkeypatch.setenv("TAVILY_API_KEY", "key")

    names = {collector.name for collector in default_collectors(use_live_network=True)}

    assert "Crunchbase" not in names
    assert "Brave Search" not in names
    assert "Tavily" in names


def test_briefing_payload_cache_round_trips(tmp_path):
    from internet_radar.storage.models import BriefingPayload, SignalRecord
    from internet_radar.storage.payload_cache import load_briefing_payload, payload_cache_age_seconds, save_briefing_payload

    payload = BriefingPayload(
        active_sources=1,
        signals_24h=1,
        top_signals=[SignalRecord(id="cache:1", topic="mcp", title="MCP repo", source="GitHub", category="code")],
        source_health={"GitHub": "ok (1)"},
        source_counts={"GitHub": 1},
        source_durations_seconds={"GitHub": 0.1},
        collection_mode="live",
    )
    path = tmp_path / "payload.json"

    save_briefing_payload(payload, path)
    restored = load_briefing_payload(path)

    assert restored is not None
    assert restored.loaded_from_cache is True
    assert restored.top_signals[0].title == "MCP repo"
    assert payload_cache_age_seconds(path) is not None
