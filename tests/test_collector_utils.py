from __future__ import annotations


def test_rate_limiter_tracks_per_source_waits_without_real_sleep():
    from internet_radar.utils.rate_limiter import SourceRateLimiter

    sleeps: list[float] = []
    current = {"time": 100.0}

    def now() -> float:
        return current["time"]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current["time"] += seconds

    limiter = SourceRateLimiter(default_interval_seconds=2.0, now=now, sleep=sleep)

    limiter.wait("GitHub")
    limiter.wait("GitHub")
    current["time"] += 0.5
    limiter.wait("GitHub")
    limiter.wait("Reddit")

    assert sleeps == [2.0, 1.5]
    assert limiter.last_access["github"] == 104.0
    assert limiter.last_access["reddit"] == 104.0


def test_proxy_rotator_cycles_enabled_proxies_and_ignores_blanks():
    from internet_radar.utils.proxy_rotator import ProxyRotator

    rotator = ProxyRotator(["", "http://one.example:8080", "http://two.example:8080"])

    assert rotator.next_proxy() == "http://one.example:8080"
    assert rotator.next_proxy() == "http://two.example:8080"
    assert rotator.next_proxy() == "http://one.example:8080"
    assert rotator.requests_kwargs() == {"proxies": {"http": "http://two.example:8080", "https": "http://two.example:8080"}}


def test_html_cleaner_removes_scripts_styles_and_collapses_text():
    from internet_radar.utils.html_cleaner import clean_html, extract_links

    raw = """
    <html>
      <head><style>.ad { display:none }</style><script>alert('x')</script></head>
      <body><nav>Menu</nav><main><h1>Agent Tools</h1><p>Browser&nbsp;automation &amp; local LLM.</p>
      <a href="/jobs">Jobs</a></main></body>
    </html>
    """

    assert clean_html(raw) == "Agent Tools Browser automation & local LLM. Jobs"
    assert extract_links(raw, base_url="https://example.com/root") == ["https://example.com/jobs"]


def test_http_collector_uses_rate_limiter_and_proxy_rotator():
    from internet_radar.collectors.base import HTTPCollector
    from internet_radar.utils.proxy_rotator import ProxyRotator
    from internet_radar.utils.rate_limiter import SourceRateLimiter

    calls: list[dict[str, object]] = []

    class FakeResponse:
        text = "ok"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, bool]:
            return {"ok": True}

    def fake_get(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    limiter = SourceRateLimiter(default_interval_seconds=0)
    collector = HTTPCollector(
        name="GitHub Search",
        category="code",
        rate_limiter=limiter,
        proxy_rotator=ProxyRotator(["http://proxy.example:8080"]),
        http_get=fake_get,
    )

    assert collector.get_json("https://api.example.com/search", q="agents") == {"ok": True}
    assert calls[0]["params"] == {"q": "agents"}
    assert calls[0]["proxies"] == {"http": "http://proxy.example:8080", "https": "http://proxy.example:8080"}
    assert "github search" in limiter.last_access


def test_http_collector_caches_json_and_text_by_url_and_params():
    from internet_radar.collectors.base import HTTPCollector

    calls: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        def __init__(self, index: int) -> None:
            self.index = index
            self.text = f"text-{index}"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, int]:
            return {"index": self.index}

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(len(calls))

    collector = HTTPCollector(name="Cached Source", category="news", http_get=fake_get, cache_ttl_seconds=60)

    assert collector.get_json("https://api.example.com/search", q="agents") == {"index": 1}
    assert collector.get_json("https://api.example.com/search", q="agents") == {"index": 1}
    assert collector.get_json("https://api.example.com/search", q="mcp") == {"index": 2}
    assert collector.get_text("https://api.example.com/page") == "text-3"
    assert collector.get_text("https://api.example.com/page") == "text-3"
    assert len(calls) == 3
