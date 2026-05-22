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
    assert RadarStore(db_path).list_signals()[0].source == "Fake Collector"


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
    } <= names
