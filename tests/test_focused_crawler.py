from __future__ import annotations


def test_load_crawl_seeds_accepts_yaml_and_sanitizes_categories(tmp_path):
    from internet_radar.collectors.focused_crawler import load_crawl_seeds

    seed_file = tmp_path / "crawl_seeds.yaml"
    seed_file.write_text(
        """
seeds:
  - name: Careers
    url: https://example.com/jobs
    category: jobs
    topic: ai internships
    score: 71
    max_pages: 3
    follow_links: true
    include_patterns:
      - /jobs
  - name: Bad Category
    url: https://example.com/other
    category: invalid
  - name: Bad URL
    url: file:///tmp/nope
    category: news
""",
        encoding="utf-8",
    )

    seeds = load_crawl_seeds(seed_file)

    assert [seed.name for seed in seeds] == ["Careers", "Bad Category"]
    assert seeds[0].category == "jobs"
    assert seeds[0].follow_links is True
    assert seeds[0].include_patterns == ["/jobs"]
    assert seeds[1].category == "search"


def test_extract_crawled_page_uses_trafilatura_text_and_scrapy_links():
    from internet_radar.collectors.focused_crawler import CrawlSeed, crawled_page_to_signal, extract_crawled_page

    html = """
    <html>
      <head><title>AI Internship Board</title></head>
      <body>
        <nav>Skip me</nav>
        <main>
          <h1>AI Internship Board</h1>
          <p>Fresh machine learning internship roles for students.</p>
          <a href="/jobs/ml-intern">ML Intern</a>
          <a href="/about">About</a>
        </main>
      </body>
    </html>
    """
    seed = CrawlSeed(
        name="Career Seeds",
        url="https://example.com/jobs",
        category="jobs",
        topic="ai internships",
        include_patterns=["/jobs"],
    )

    page = extract_crawled_page(html, "https://example.com/jobs", seed)
    signal = crawled_page_to_signal(page, seed)

    assert page.title == "AI Internship Board"
    assert "machine learning internship" in page.text.lower()
    assert page.links == ["https://example.com/jobs/ml-intern"]
    assert signal.source == "Focused Web Crawler"
    assert signal.category == "jobs"
    assert signal.metadata["extractor"] == "scrapy+trafilatura"
    assert "Fresh machine learning internship" in signal.summary


def test_focused_web_crawler_respects_robots_and_does_not_store_raw_html():
    from internet_radar.collectors.focused_crawler import CrawlSeed, FocusedWebCrawlerCollector

    calls: list[str] = []

    class FakeResponse:
        def __init__(self, text: str) -> None:
            self.text = text

        def raise_for_status(self) -> None:
            return None

    def fake_get(url, **kwargs):
        calls.append(url)
        if url.endswith("/robots.txt"):
            return FakeResponse("User-agent: *\nDisallow: /blocked\n")
        return FakeResponse("<html><title>Visible Crawler Page</title><main>Useful public signal text for radar.</main></html>")

    collector = FocusedWebCrawlerCollector(
        seeds=[
            CrawlSeed(name="Blocked", url="https://example.com/blocked", category="news"),
            CrawlSeed(name="Allowed", url="https://example.com/allowed", category="news"),
        ],
        max_total_pages=4,
        max_pages_per_seed=1,
        respect_robots=True,
    )
    collector.http_get = fake_get
    collector.rate_limiter = None

    records = collector.collect()

    assert calls == ["https://example.com/robots.txt", "https://example.com/allowed"]
    assert [record.title for record in records] == ["Visible Crawler Page"]
    assert "raw_html" not in records[0].metadata
    assert records[0].metadata["text_chars"] > 0


def test_focused_crawler_is_part_of_free_live_collectors(monkeypatch):
    from internet_radar.collectors.focused_crawler import FocusedWebCrawlerCollector
    from internet_radar.collectors.live import default_collectors
    from internet_radar.sources.registry import enabled_sources
    from internet_radar.utils.rate_limiter import DEFAULT_SOURCE_INTERVALS

    monkeypatch.setenv("INTERNET_RADAR_ENABLE_CRAWLER", "1")

    collectors = default_collectors(use_live_network=True)

    assert any(isinstance(collector, FocusedWebCrawlerCollector) for collector in collectors)
    assert "Focused Web Crawler" in {source.name for source in enabled_sources()}
    assert DEFAULT_SOURCE_INTERVALS["focused web crawler"] == 5.0


def test_focused_crawler_defaults_are_useful_for_live_collection(monkeypatch):
    from internet_radar.collectors.focused_crawler import FocusedWebCrawlerCollector

    monkeypatch.delenv("INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED", raising=False)
    monkeypatch.delenv("INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS", raising=False)

    collector = FocusedWebCrawlerCollector(seeds=[])

    assert collector.max_total_pages == 200
    assert collector.max_pages_per_seed == 20
    assert collector.timeout == 20.0


def test_bundled_crawl_seeds_target_high_value_radar_pages():
    from internet_radar.collectors.focused_crawler import load_crawl_seeds

    seeds = load_crawl_seeds("config/crawl_seeds.yaml")
    names = {seed.name for seed in seeds}

    assert {
        "Devpost Hackathons",
        "Unstop Hackathons",
        "Dare2Compete Hackathons",
        "HackerEarth Hackathons",
        "Hackaday Blog",
        "Make Magazine",
        "IEEE Spectrum Robotics",
        "HN New Posts",
        "Indie Hackers Posts",
        "TechCrunch Startups",
        "Papers With Code Latest",
        "HuggingFace Blog",
        "RemoteOK Jobs",
        "Wellfound Jobs",
    }.issubset(names)
    assert {seed.category for seed in seeds} >= {"hackathons", "code", "social", "news", "research", "jobs"}
    assert all(seed.max_pages >= 20 for seed in seeds)
    assert any(seed.follow_links for seed in seeds)
