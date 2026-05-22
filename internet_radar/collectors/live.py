from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from typing import Any

from internet_radar.collectors.base import HTTPCollector
from internet_radar.storage.models import SignalRecord


DEFAULT_TOPICS = ["browser agents", "local llm", "mcp", "streamlit", "agentic ai"]


def infer_topic(title: str) -> str:
    cleaned = re.sub(r"^(show hn:|ask hn:|launch hn:)\s*", "", title.strip(), flags=re.I)
    cleaned = re.sub(r"[^A-Za-z0-9.+# -]+", "", cleaned).strip().lower()
    words = cleaned.split()
    return " ".join(words[:5]) if words else "technology trend"


def parse_hackernews_items(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = html.unescape(str(item.get("title") or "Untitled HN item"))
        points = int(item.get("score") or item.get("points") or 0)
        comments = int(item.get("descendants") or item.get("num_comments") or 0)
        score = min(points // 3 + comments // 2, 100)
        records.append(
            SignalRecord(
                id=f"hn:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Hacker News",
                category="social",
                url=str(item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id', '')}"),
                score=score,
                velocity=points,
                metadata={"comments": comments},
            )
        )
    return records


def parse_devto_articles(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("title") or "Dev.to article")
        reactions = int(item.get("public_reactions_count") or 0)
        tags = item.get("tag_list") or []
        records.append(
            SignalRecord(
                id=f"devto:{item.get('id', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=title,
                source="Dev.to",
                category="news",
                url=str(item.get("url") or ""),
                score=min(35 + reactions, 100),
                velocity=reactions,
                metadata={"tags": tags},
            )
        )
    return records


def parse_remoteok_jobs(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        if not item.get("position"):
            continue
        title = f"{item.get('position')} at {item.get('company', 'Unknown')}"
        tags = [str(tag).lower() for tag in item.get("tags") or []]
        score = 70 if any(tag in {"ai", "python", "ml", "machine learning"} for tag in tags) else 55
        records.append(
            SignalRecord(
                id=f"remoteok:{item.get('id', title)}",
                topic=infer_topic(" ".join(tags) if tags else str(item.get("position"))),
                title=title,
                source="RemoteOK",
                category="jobs",
                url=str(item.get("url") or ""),
                score=score,
                velocity=score,
                metadata={"tags": tags},
            )
        )
    return records


def parse_arxiv_feed(text: str) -> list[SignalRecord]:
    root = ET.fromstring(text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    records: list[SignalRecord] = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        url = entry.findtext("atom:id", default="", namespaces=ns) or ""
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"arxiv:{url or title}",
                topic=infer_topic(title),
                title=title,
                source="arXiv",
                category="research",
                url=url,
                score=72,
                velocity=1,
                summary=summary[:280],
            )
        )
    return records


def parse_github_repositories(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("full_name") or item.get("name") or "GitHub repository")
        stars = int(item.get("stargazers_count") or 0)
        records.append(
            SignalRecord(
                id=f"github:{item.get('id', title)}",
                topic=infer_topic(" ".join(item.get("topics") or []) or title),
                title=title,
                source="GitHub Search",
                category="code",
                url=str(item.get("html_url") or ""),
                score=min(50 + stars // 500, 100),
                velocity=stars,
                summary=str(item.get("description") or "")[:280],
                metadata={"language": item.get("language"), "stars": stars},
            )
        )
    return records


def parse_reddit_children(children: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for child in children:
        item = child.get("data", child)
        title = str(item.get("title") or "Reddit discussion")
        ups = int(item.get("ups") or item.get("score") or 0)
        records.append(
            SignalRecord(
                id=f"reddit:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Reddit JSON",
                category="social",
                url=f"https://reddit.com{item.get('permalink', '')}" if item.get("permalink") else str(item.get("url") or ""),
                score=min(40 + ups // 10, 100),
                velocity=ups,
                metadata={"subreddit": item.get("subreddit")},
            )
        )
    return records


def parse_rss_entries(text: str) -> list[SignalRecord]:
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", text, flags=re.I | re.S)
    links = re.findall(r"<link>(.*?)</link>", text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    for index, title_pair in enumerate(titles[1:8]):
        title = html.unescape(next((part for part in title_pair if part), "")).strip()
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"rss:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="Tech RSS",
                category="news",
                url=links[index + 1] if index + 1 < len(links) else "",
                score=58,
                velocity=1,
            )
        )
    return records


class GitHubSearchCollector(HTTPCollector):
    def __init__(self, topic: str = "agentic ai") -> None:
        super().__init__(name="GitHub Search", category="code")
        self.topic = topic

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(
                "https://api.github.com/search/repositories",
                q=f"{self.topic} pushed:>2026-01-01",
                sort="stars",
                order="desc",
                per_page=8,
            )
            return parse_github_repositories(list(data.get("items", [])))  # type: ignore[union-attr]
        except Exception:
            return sample_signals("code")


class HackerNewsCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Hacker News", category="social")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://hn.algolia.com/api/v1/search", tags="front_page", hitsPerPage=8)
            hits = list(data.get("hits", []))  # type: ignore[union-attr]
            return parse_hackernews_items(hits)
        except Exception:
            return sample_signals("social")


class RedditJSONCollector(HTTPCollector):
    def __init__(self, subreddit: str = "LocalLLaMA") -> None:
        super().__init__(name="Reddit JSON", category="social")
        self.subreddit = subreddit

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(f"https://www.reddit.com/r/{self.subreddit}/hot.json", limit=8)
            children = data.get("data", {}).get("children", [])  # type: ignore[union-attr]
            return parse_reddit_children(list(children))
        except Exception:
            return sample_signals("social")


class DevToCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Dev.to", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://dev.to/api/articles", tag="ai", top=7, per_page=8)
            return parse_devto_articles(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("news")


class RemoteOKCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="RemoteOK", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://remoteok.com/api")
            return parse_remoteok_jobs(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("jobs")


class ArxivCollector(HTTPCollector):
    def __init__(self, query: str = "agentic AI") -> None:
        super().__init__(name="arXiv", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text(
                "https://export.arxiv.org/api/query",
                search_query=f"all:{self.query}",
                start=0,
                max_results=8,
                sortBy="submittedDate",
                sortOrder="descending",
            )
            return parse_arxiv_feed(text)
        except Exception:
            return sample_signals("research")


class PackageCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Package Velocity", category="code")

    def collect(self) -> list[SignalRecord]:
        signals: list[SignalRecord] = []
        for package in ["ollama", "streamlit", "playwright"]:
            signals.append(
                SignalRecord(
                    id=f"package:{package}",
                    topic=package,
                    title=f"{package} package ecosystem signal",
                    source="npm/PyPI",
                    category="code",
                    url=f"https://pypi.org/project/{package}/",
                    score=64,
                    velocity=1,
                )
            )
        return signals


def default_collectors(use_live_network: bool = True) -> list[object]:
    if not use_live_network:
        return [SampleCollector()]
    return [
        GitHubSearchCollector(),
        HackerNewsCollector(),
        RedditJSONCollector(),
        DevToCollector(),
        RemoteOKCollector(),
        ArxivCollector(),
        PackageCollector(),
    ]


class SampleCollector:
    name = "Sample Radar"
    category = "mixed"

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for category in ["code", "social", "news", "jobs", "research", "finance", "app_stores"]:
            records.extend(sample_signals(category))
        return records


def sample_signals(category: str) -> list[SignalRecord]:
    now = datetime.now(UTC)
    samples = {
        "code": [
            ("browser agents", "Browser automation agents gain repository momentum", "GitHub Search", 88, "https://github.com/search?q=browser+agents"),
            ("mcp", "MCP servers directory keeps expanding", "GitHub Search", 82, "https://github.com/modelcontextprotocol/servers"),
        ],
        "social": [
            ("local llm", "Developers discuss local LLM workflows", "Hacker News", 76, "https://news.ycombinator.com"),
            ("browser agents", "Reddit asks how to run browser agents locally", "Reddit JSON", 71, "https://reddit.com"),
        ],
        "news": [
            ("streamlit", "Python dashboards remain fast path for internal AI tools", "Dev.to", 68, "https://dev.to"),
        ],
        "jobs": [
            ("ai intern", "AI intern role mentions agents and automation", "RemoteOK", 79, "https://remoteok.com"),
        ],
        "research": [
            ("agentic browser automation", "Agentic browser automation papers increase", "arXiv", 77, "https://arxiv.org"),
        ],
        "finance": [
            ("ai infrastructure", "Funding pulse favors AI infrastructure tooling", "YC Companies", 73, "https://www.ycombinator.com/companies"),
        ],
        "app_stores": [
            ("ai assistant pain", "Users complain about expensive AI assistant subscriptions", "iTunes App Store", 66, "https://itunes.apple.com"),
        ],
    }
    return [
        SignalRecord(
            id=f"sample:{category}:{index}",
            topic=topic,
            title=title,
            source=source,
            category=category,  # type: ignore[arg-type]
            url=url,
            score=score,
            velocity=max(score - 50, 1),
            observed_at=now,
        )
        for index, (topic, title, source, score, url) in enumerate(samples.get(category, []))
    ]
