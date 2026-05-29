from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from urllib.parse import urldefrag, urlparse
from urllib.robotparser import RobotFileParser

import trafilatura
import yaml
from scrapy.http import HtmlResponse
from scrapy.linkextractors import LinkExtractor

from internet_radar.collectors.base import HTTPCollector
from internet_radar.storage.models import Category, SignalRecord


DEFAULT_CRAWL_SEEDS_PATH = Path("config/crawl_seeds.yaml")
VALID_SIGNAL_CATEGORIES: set[str] = {
    "code",
    "social",
    "news",
    "jobs",
    "hackathons",
    "research",
    "finance",
    "search",
    "app_stores",
}


@dataclass(frozen=True)
class CrawlSeed:
    name: str
    url: str
    category: str
    topic: str = ""
    score: int = 58
    max_pages: int = 1
    follow_links: bool = False
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CrawledPage:
    url: str
    title: str
    text: str
    links: list[str]
    content_hash: str


class FocusedWebCrawlerCollector(HTTPCollector):
    def __init__(
        self,
        seeds: list[CrawlSeed] | None = None,
        seed_path: str | Path | None = None,
        max_total_pages: int | None = None,
        max_pages_per_seed: int | None = None,
        respect_robots: bool | None = None,
    ) -> None:
        timeout = float(os.getenv("INTERNET_RADAR_CRAWLER_TIMEOUT_SECONDS", "20"))
        super().__init__(name="Focused Web Crawler", category="search", timeout=timeout, cache_ttl_seconds=900)
        self.seeds = seeds if seeds is not None else load_crawl_seeds(seed_path)
        self.max_total_pages = max_total_pages if max_total_pages is not None else _env_int("INTERNET_RADAR_CRAWLER_MAX_TOTAL_PAGES", 200)
        self.max_pages_per_seed = max_pages_per_seed if max_pages_per_seed is not None else _env_int("INTERNET_RADAR_CRAWLER_MAX_PAGES_PER_SEED", 20)
        self.respect_robots = respect_robots if respect_robots is not None else _env_bool("INTERNET_RADAR_CRAWLER_RESPECT_ROBOTS", True)
        self._robots_cache: dict[str, RobotFileParser | None] = {}

    def collect(self) -> list[SignalRecord]:
        if not _env_bool("INTERNET_RADAR_ENABLE_CRAWLER", True):
            return []
        records: list[SignalRecord] = []
        visited: set[str] = set()
        total_pages = 0
        for seed in self.seeds:
            if total_pages >= self.max_total_pages:
                break
            seed_limit = max(1, min(seed.max_pages, self.max_pages_per_seed, self.max_total_pages - total_pages))
            queue = [_normalize_url(seed.url)]
            seed_pages = 0
            while queue and seed_pages < seed_limit and total_pages < self.max_total_pages:
                url = queue.pop(0)
                if not url or url in visited:
                    continue
                visited.add(url)
                if self.respect_robots and not self._allowed_by_robots(url):
                    continue
                try:
                    html_text = self.get_text(url)
                    page = extract_crawled_page(html_text, url, seed)
                except Exception:
                    continue
                if page.title or page.text:
                    records.append(crawled_page_to_signal(page, seed))
                    seed_pages += 1
                    total_pages += 1
                if seed.follow_links:
                    queue.extend(
                        link
                        for link in page.links
                        if link not in visited and _same_host(link, seed.url) and _seed_allows_link(seed, link)
                    )
        return records

    def _allowed_by_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._robots_cache:
            robots = RobotFileParser()
            robots.set_url(f"{base}/robots.txt")
            try:
                robots_text = self.get_text(f"{base}/robots.txt")
                robots.parse(robots_text.splitlines())
                self._robots_cache[base] = robots
            except Exception:
                self._robots_cache[base] = None
        parser = self._robots_cache[base]
        if parser is None:
            return True
        return parser.can_fetch(os.getenv("INTERNET_RADAR_USER_AGENT", "internet-radar-v2/0.1"), url)


def load_crawl_seeds(path: str | Path | None = None) -> list[CrawlSeed]:
    selected_path = Path(path or os.getenv("INTERNET_RADAR_CRAWL_SEEDS", str(DEFAULT_CRAWL_SEEDS_PATH)))
    if not selected_path.exists():
        return []
    raw = yaml.safe_load(selected_path.read_text(encoding="utf-8")) or {}
    entries = raw.get("seeds", raw) if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return []
    seeds = [_seed_from_mapping(entry) for entry in entries if isinstance(entry, dict)]
    return [seed for seed in seeds if seed is not None]


def extract_crawled_page(html_text: str, url: str, seed: CrawlSeed | None = None) -> CrawledPage:
    response = HtmlResponse(url=url, body=html_text.encode("utf-8", errors="ignore"), encoding="utf-8")
    title = _first_text(
        [
            response.css("meta[property='og:title']::attr(content)").get(),
            response.css("title::text").get(),
            response.css("h1::text").get(),
        ]
    )
    text = trafilatura.extract(
        html_text,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    ) or _scrapy_text_fallback(response)
    text = _compact_text(text)
    links = _extract_links(response, seed)
    content_hash = hashlib.sha1(f"{url}|{title}|{text[:4000]}".encode("utf-8")).hexdigest()
    return CrawledPage(url=url, title=title, text=text, links=links, content_hash=content_hash)


def crawled_page_to_signal(page: CrawledPage, seed: CrawlSeed) -> SignalRecord:
    title = page.title or seed.name
    text = page.text
    score = min(seed.score + min(len(text) // 800, 12) + min(len(page.links), 20) // 5, 100)
    return SignalRecord(
        id=f"crawler:{page.content_hash[:20]}",
        topic=seed.topic or _infer_topic(f"{title} {text[:160]}"),
        title=title,
        source="Focused Web Crawler",
        category=cast(Category, seed.category),
        url=page.url,
        score=score,
        velocity=max(len(page.links), 1),
        summary=text[:280],
        metadata={
            "crawler_seed": seed.name,
            "content_hash": page.content_hash,
            "text_chars": len(text),
            "links_found": len(page.links),
            "extractor": "scrapy+trafilatura",
        },
    )


def _seed_from_mapping(entry: dict[str, Any]) -> CrawlSeed | None:
    url = str(entry.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return None
    category = str(entry.get("category") or "search").strip()
    if category not in VALID_SIGNAL_CATEGORIES:
        category = "search"
    return CrawlSeed(
        name=str(entry.get("name") or urlparse(url).netloc or "Crawler Seed").strip(),
        url=url,
        category=category,
        topic=str(entry.get("topic") or "").strip(),
        score=max(0, min(_to_int(entry.get("score"), 58), 100)),
        max_pages=max(1, _to_int(entry.get("max_pages"), 1)),
        follow_links=_to_bool(entry.get("follow_links"), False),
        include_patterns=[str(pattern) for pattern in entry.get("include_patterns") or []],
        exclude_patterns=[str(pattern) for pattern in entry.get("exclude_patterns") or []],
    )


def _extract_links(response: HtmlResponse, seed: CrawlSeed | None) -> list[str]:
    extractor = LinkExtractor(
        allow=tuple(seed.include_patterns if seed else ()),
        deny=tuple(seed.exclude_patterns if seed else ()),
        unique=True,
    )
    links = []
    for link in extractor.extract_links(response):
        normalized = _normalize_url(link.url)
        if normalized.startswith(("http://", "https://")):
            links.append(normalized)
    return links


def _scrapy_text_fallback(response: HtmlResponse) -> str:
    parts = [
        value.strip()
        for value in response.css("main ::text, article ::text, body ::text").getall()
        if value and value.strip()
    ]
    return " ".join(parts)


def _first_text(values: list[str | None]) -> str:
    for value in values:
        text = _compact_text(str(value or ""))
        if text:
            return text
    return ""


def _compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _normalize_url(url: str) -> str:
    return urldefrag(str(url).strip())[0]


def _same_host(url: str, seed_url: str) -> bool:
    return urlparse(url).netloc == urlparse(seed_url).netloc


def _seed_allows_link(seed: CrawlSeed, url: str) -> bool:
    if seed.exclude_patterns and any(re.search(pattern, url) for pattern in seed.exclude_patterns):
        return False
    return not seed.include_patterns or any(re.search(pattern, url) for pattern in seed.include_patterns)


def _infer_topic(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.+# -]+", "", text.strip()).lower()
    words = cleaned.split()
    return " ".join(words[:5]) if words else "web signal"


def _to_int(value: object, default: int) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    return max(1, _to_int(os.getenv(name), default))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return _to_bool(value, default)


def _to_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}
