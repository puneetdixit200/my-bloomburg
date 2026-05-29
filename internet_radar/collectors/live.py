from __future__ import annotations

import hashlib
import html
import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests
import yaml

from internet_radar.collectors.base import HTTPCollector
from internet_radar.collectors.focused_crawler import FocusedWebCrawlerCollector
from internet_radar.special.radar import build_special_signals
from internet_radar.storage.models import SignalRecord


DEFAULT_TOPICS = ["browser agents", "local llm", "mcp", "streamlit", "agentic ai"]
DEFAULT_REDDIT_SUBREDDITS = ["LocalLLaMA", "MachineLearning", "OpenAI", "learnpython", "webdev"]
HttpPost = Callable[..., Any]


def infer_topic(title: str) -> str:
    cleaned = re.sub(r"^(show hn:|ask hn:|launch hn:)\s*", "", title.strip(), flags=re.I)
    cleaned = re.sub(r"[^A-Za-z0-9.+# -]+", "", cleaned).strip().lower()
    words = cleaned.split()
    return " ".join(words[:5]) if words else "technology trend"


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _payload_list(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get(key, [])
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


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


def parse_rss_entries(text: str, source_name: str = "Tech RSS") -> list[SignalRecord]:
    titles = re.findall(r"<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>", text, flags=re.I | re.S)
    links = re.findall(r"<link>(.*?)</link>", text, flags=re.I | re.S)
    summaries = re.findall(
        r"<description><!\[CDATA\[(.*?)\]\]></description>|<description>(.*?)</description>",
        text,
        flags=re.I | re.S,
    )
    records: list[SignalRecord] = []
    for index, title_pair in enumerate(titles[1:8]):
        title = html.unescape(next((part for part in title_pair if part), "")).strip()
        if not title:
            continue
        summary = _clean_html(next((part for part in summaries[index + 1] if part), "")) if index + 1 < len(summaries) else ""
        records.append(
            SignalRecord(
                id=f"rss:{source_name}:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source=source_name,
                category="news",
                url=links[index + 1] if index + 1 < len(links) else "",
                score=58,
                velocity=1,
                summary=summary[:280],
            )
        )
    return records


def parse_crates_results(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "crates"):
        name = str(item.get("name") or "Rust crate")
        downloads = _as_int(item.get("downloads"))
        recent = _as_int(item.get("recent_downloads"))
        records.append(
            SignalRecord(
                id=f"crates:{item.get('id', name)}",
                topic=infer_topic(name),
                title=f"{name} Rust crate velocity",
                source="crates.io",
                category="code",
                url=f"https://crates.io/crates/{name}",
                score=min(58 + recent // 10_000 + downloads // 1_000_000, 100),
                velocity=max(recent, downloads, 1),
                summary=str(item.get("description") or "")[:280],
                metadata={"downloads": downloads, "recent_downloads": recent},
            )
        )
    return records


def parse_bluesky_posts(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "posts"):
        record = item.get("record") or {}
        author = item.get("author") or {}
        text = str(record.get("text") or item.get("text") or "Bluesky post")
        likes = _as_int(item.get("likeCount"))
        replies = _as_int(item.get("replyCount"))
        reposts = _as_int(item.get("repostCount"))
        records.append(
            SignalRecord(
                id=f"bluesky:{item.get('uri', text)}",
                topic=infer_topic(text),
                title=text[:120],
                source="Bluesky",
                category="social",
                url=str(item.get("uri") or ""),
                score=min(50 + likes + replies * 2 + reposts, 100),
                velocity=likes + replies + reposts,
                summary=text[:280],
                metadata={"author": author.get("handle"), "likes": likes, "replies": replies, "reposts": reposts},
            )
        )
    return records


def parse_mastodon_statuses(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        content = _clean_html(str(item.get("content") or "Mastodon status"))
        account = item.get("account") or {}
        reblogs = _as_int(item.get("reblogs_count"))
        favourites = _as_int(item.get("favourites_count"))
        replies = _as_int(item.get("replies_count"))
        records.append(
            SignalRecord(
                id=f"mastodon:{item.get('id', content)}",
                topic=infer_topic(content),
                title=content[:120] or "Mastodon trend",
                source="Mastodon",
                category="social",
                url=str(item.get("url") or ""),
                score=min(48 + reblogs * 2 + favourites + replies * 2, 100),
                velocity=reblogs + favourites + replies,
                summary=content[:280],
                metadata={"account": account.get("acct"), "reblogs": reblogs, "favourites": favourites, "replies": replies},
            )
        )
    return records


def parse_hashnode_posts(payload: dict[str, Any]) -> list[SignalRecord]:
    candidates = (
        (((payload.get("data") or {}).get("storiesFeed") or {}).get("edges") or [])
        or (((payload.get("data") or {}).get("feed") or {}).get("edges") or [])
    )
    records: list[SignalRecord] = []
    for edge in candidates:
        node = edge.get("node", edge) if isinstance(edge, dict) else {}
        if not isinstance(node, dict):
            continue
        title = str(node.get("title") or "Hashnode article")
        reactions = _as_int(node.get("reactionCount"))
        responses = _as_int(node.get("responseCount"))
        tags = [str(tag.get("name", "")) for tag in node.get("tags") or [] if isinstance(tag, dict)]
        records.append(
            SignalRecord(
                id=f"hashnode:{node.get('id', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=title,
                source="Hashnode",
                category="news",
                url=str(node.get("url") or ""),
                score=min(55 + reactions + responses * 2, 100),
                velocity=reactions + responses,
                summary=str(node.get("brief") or "")[:280],
                metadata={"tags": [tag for tag in tags if tag]},
            )
        )
    return records


def parse_mlh_events_html(text: str) -> list[SignalRecord]:
    cards = re.findall(r'<a[^>]+href="([^"]+)"[^>]*class="[^"]*event[^"]*"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    for index, (url, card_html) in enumerate(cards[:10]):
        title_match = re.search(r"<h[23][^>]*>(.*?)</h[23]>", card_html, flags=re.I | re.S)
        title = _clean_html(title_match.group(1) if title_match else card_html)
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"mlh:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="MLH",
                category="hackathons",
                url=url if url.startswith("http") else f"https://mlh.io{url}",
                score=65,
                velocity=1,
            )
        )
    return records


def parse_leetcode_contests(payload: dict[str, Any]) -> list[SignalRecord]:
    contests = (((payload.get("data") or {}).get("allContests")) or _payload_list(payload, "contests") or [])
    records: list[SignalRecord] = []
    for item in contests[:10]:
        title = str(item.get("title") or "LeetCode contest")
        start = _as_int(item.get("startTime") or item.get("originStartTime"))
        records.append(
            SignalRecord(
                id=f"leetcode:{item.get('titleSlug', title)}",
                topic=infer_topic(title),
                title=title,
                source="LeetCode Contests",
                category="hackathons",
                url=f"https://leetcode.com/contest/{item.get('titleSlug', '')}",
                score=64,
                velocity=max(start, 1),
                metadata={"start_time": start, "duration": item.get("duration")},
            )
        )
    return records


def parse_yahoo_quote(payload: dict[str, Any]) -> list[SignalRecord]:
    results = (((payload.get("quoteResponse") or {}).get("result")) or [])
    records: list[SignalRecord] = []
    for item in results:
        symbol = str(item.get("symbol") or "stock")
        change = _as_float(item.get("regularMarketChangePercent"))
        price = _as_float(item.get("regularMarketPrice"))
        records.append(
            SignalRecord(
                id=f"yahoo-finance:{symbol}",
                topic=infer_topic(str(item.get("longName") or symbol)),
                title=f"{symbol} market momentum",
                source="Yahoo Finance",
                category="finance",
                url=f"https://finance.yahoo.com/quote/{symbol}",
                score=min(60 + int(abs(change) * 3), 100),
                velocity=change,
                metadata={"price": price, "change_percent": change},
            )
        )
    return records


def parse_wayback_available(payload: dict[str, Any], target_url: str) -> list[SignalRecord]:
    snapshot = ((payload.get("archived_snapshots") or {}).get("closest") or {})
    if not snapshot:
        return []
    status = str(snapshot.get("status") or "")
    timestamp = str(snapshot.get("timestamp") or "")
    return [
        SignalRecord(
            id=f"wayback:{target_url}:{timestamp}",
            topic=infer_topic(target_url),
            title=f"{target_url} has recent Wayback coverage",
            source="Wayback Machine",
            category="search",
            url=str(snapshot.get("url") or ""),
            score=65 if status == "200" else 55,
            velocity=1,
            metadata={"status": status, "timestamp": timestamp, "available": bool(snapshot.get("available", True))},
        )
    ]


def parse_playstore_search_html(text: str) -> list[SignalRecord]:
    matches = re.findall(r'href="(/store/apps/details\?id=([^"&]+)[^"]*)".{0,500}?>([^<>]{3,120})<', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    seen: set[str] = set()
    for index, (path, app_id, title_html) in enumerate(matches[:10]):
        if app_id in seen:
            continue
        seen.add(app_id)
        title = _clean_html(title_html)
        if not title:
            continue
        records.append(
            SignalRecord(
                id=f"google-play:{app_id}",
                topic=infer_topic(title),
                title=title,
                source="Google Play",
                category="app_stores",
                url=f"https://play.google.com{html.unescape(path)}",
                score=58,
                velocity=max(1, 10 - index),
            )
        )
    return records


def parse_github_trending_html(text: str) -> list[SignalRecord]:
    links = re.findall(r'<h2[^>]*>.*?<a[^>]+href="/([^"/]+/[^"/]+)"[^>]*>(.*?)</a>.*?</h2>', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    for index, (repo_path, label_html) in enumerate(links[:10]):
        repo = _clean_html(label_html).replace(" ", "")
        if "/" not in repo:
            repo = repo_path
        records.append(
            SignalRecord(
                id=f"github-trending:{repo.lower()}",
                topic=infer_topic(repo),
                title=f"{repo} is trending on GitHub",
                source="GitHub Trending",
                category="code",
                url=f"https://github.com/{repo_path}",
                score=max(78 - index, 60),
                velocity=max(1, 10 - index),
            )
        )
    return records


def parse_hn_algolia_hits(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = html.unescape(str(item.get("title") or item.get("story_title") or "HN Algolia story"))
        points = _as_int(item.get("points"))
        comments = _as_int(item.get("num_comments"))
        object_id = item.get("objectID") or item.get("story_id") or title
        records.append(
            SignalRecord(
                id=f"hn-algolia:{object_id}",
                topic=infer_topic(title),
                title=title,
                source="HN Algolia",
                category="social",
                url=str(item.get("url") or f"https://news.ycombinator.com/item?id={object_id}"),
                score=min(45 + points // 5 + comments // 3, 100),
                velocity=points + comments,
                metadata={"points": points, "comments": comments},
            )
        )
    return records


def parse_tldr_html(text: str) -> list[SignalRecord]:
    candidates = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    seen: set[str] = set()
    for index, (url, label_html) in enumerate(candidates[:40]):
        title = _clean_html(label_html)
        if len(title) < 8 or title.lower() in seen:
            continue
        seen.add(title.lower())
        records.append(
            SignalRecord(
                id=f"tldr:{hashlib.sha1(title.encode('utf-8')).hexdigest()[:12]}",
                topic=infer_topic(title),
                title=title[:140],
                source="TLDR Newsletter",
                category="news",
                url=url if url.startswith("http") else f"https://tldr.tech{url}",
                score=max(55, 70 - index),
                velocity=max(1, 10 - index),
            )
        )
        if len(records) >= 8:
            break
    return records


def parse_yc_jobs_html(text: str) -> list[SignalRecord]:
    matches = re.findall(r'href="([^"]*/jobs/[^"]*)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    seen: set[str] = set()
    for index, (url, label_html) in enumerate(matches[:12]):
        title = _clean_html(label_html)
        if len(title) < 4 or title.lower() in seen:
            continue
        seen.add(title.lower())
        records.append(
            SignalRecord(
                id=f"yc-jobs:{hashlib.sha1((url + title).encode('utf-8')).hexdigest()[:12]}",
                topic=infer_topic(title),
                title=title[:140],
                source="YC Jobs",
                category="jobs",
                url=url if url.startswith("http") else f"https://www.ycombinator.com{url}",
                score=max(60, 75 - index),
                velocity=max(1, 12 - index),
            )
        )
    return records


def parse_devpost_hackathons_html(text: str) -> list[SignalRecord]:
    cards = re.findall(r'<a[^>]+href="([^"]*hackathons/[^"]*)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    records: list[SignalRecord] = []
    seen: set[str] = set()
    for index, (url, label_html) in enumerate(cards[:20]):
        title = _clean_html(label_html)
        if len(title) < 5 or title.lower() in seen:
            continue
        seen.add(title.lower())
        records.append(
            SignalRecord(
                id=f"devpost:{hashlib.sha1((url + title).encode('utf-8')).hexdigest()[:12]}",
                topic=infer_topic(title),
                title=title[:140],
                source="Devpost",
                category="hackathons",
                url=url if url.startswith("http") else f"https://devpost.com{url}",
                score=max(70, 82 - index),
                velocity=max(1, 20 - index),
            )
        )
        if len(records) >= 10:
            break
    return records


def parse_stackoverflow_questions(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "items"):
        title = html.unescape(str(item.get("title") or "Stack Overflow question"))
        score = _as_int(item.get("score"))
        answers = _as_int(item.get("answer_count"))
        tags = [str(tag) for tag in item.get("tags") or []]
        records.append(
            SignalRecord(
                id=f"stackoverflow:{item.get('question_id', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=title,
                source="Stack Overflow",
                category="social",
                url=str(item.get("link") or ""),
                score=min(55 + score + answers * 2, 100),
                velocity=max(score + answers, 1),
                metadata={"tags": tags, "answers": answers},
            )
        )
    return records


def parse_huggingface_models(payload: list[dict[str, Any]] | dict[str, Any]) -> list[SignalRecord]:
    items = _payload_list(payload, "models") or _payload_list(payload, "items")
    records: list[SignalRecord] = []
    for item in items:
        model_id = str(item.get("modelId") or item.get("id") or "huggingface-model")
        downloads = _as_int(item.get("downloads"))
        likes = _as_int(item.get("likes"))
        tags = [str(tag) for tag in item.get("tags") or []]
        records.append(
            SignalRecord(
                id=f"huggingface-model:{model_id}",
                topic=infer_topic(" ".join(tags[:3]) if tags else model_id),
                title=f"{model_id} model velocity",
                source="Hugging Face Models",
                category="research",
                url=f"https://huggingface.co/{model_id}",
                score=min(58 + downloads // 1000 + likes // 10, 100),
                velocity=max(downloads, likes, 1),
                metadata={"downloads": downloads, "likes": likes, "tags": tags[:8]},
            )
        )
    return records


def parse_gitlab_projects(payload: list[dict[str, Any]] | dict[str, Any]) -> list[SignalRecord]:
    items = _payload_list(payload, "projects") or _payload_list(payload, "items")
    records: list[SignalRecord] = []
    for item in items:
        name = str(item.get("path_with_namespace") or item.get("name_with_namespace") or item.get("name") or "GitLab project")
        stars = _as_int(item.get("star_count"))
        records.append(
            SignalRecord(
                id=f"gitlab:{item.get('id', name)}",
                topic=infer_topic(name),
                title=name,
                source="GitLab Explore",
                category="code",
                url=str(item.get("web_url") or ""),
                score=min(55 + stars // 50, 100),
                velocity=max(stars, 1),
                summary=str(item.get("description") or "")[:280],
                metadata={"stars": stars},
            )
        )
    return records


def parse_opencollective_search(payload: dict[str, Any]) -> list[SignalRecord]:
    nodes = (((payload.get("data") or {}).get("search") or {}).get("nodes") or [])
    records: list[SignalRecord] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        slug = str(node.get("slug") or node.get("id") or node.get("name") or "collective")
        stats = node.get("stats") or {}
        total = _as_float((stats.get("totalAmountReceived") or {}).get("value") if isinstance(stats, dict) else 0)
        records.append(
            SignalRecord(
                id=f"opencollective:{slug}",
                topic=infer_topic(str(node.get("name") or slug)),
                title=f"{node.get('name') or slug} funding signal",
                source="OpenCollective",
                category="finance",
                url=f"https://opencollective.com/{slug}",
                score=min(60 + int(total // 10_000), 100) if total else 60,
                velocity=total,
                summary=str(node.get("description") or "")[:280],
                metadata={"type": node.get("type"), "total_amount_received": total},
            )
        )
    return records


def parse_mcp_servers_markdown(text: str) -> list[SignalRecord]:
    rows = re.findall(r"^\s*[-*]\s+\[([^\]]+)\]\((https?://[^)]+)\)", text, flags=re.M)
    records: list[SignalRecord] = []
    for index, (title, url) in enumerate(rows[:12]):
        records.append(
            SignalRecord(
                id=f"mcp-directory:{hashlib.sha1((title + url).encode('utf-8')).hexdigest()[:12]}",
                topic=infer_topic(title),
                title=f"{title} MCP server",
                source="MCP Servers Directory",
                category="code",
                url=url,
                score=max(60, 76 - index),
                velocity=max(1, 12 - index),
            )
        )
    return records


def parse_lobsters_stories(items: list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("title") or "Lobsters story")
        score = _as_int(item.get("score"))
        comments = _as_int(item.get("comments_count"))
        records.append(
            SignalRecord(
                id=f"lobsters:{item.get('short_id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Lobsters",
                category="news",
                url=str(item.get("url") or item.get("comments_url") or ""),
                score=min(45 + score + comments, 100),
                velocity=score + comments,
                metadata={"comments": comments},
            )
        )
    return records


def parse_themuse_jobs(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("name") or "The Muse job")
        company = str((item.get("company") or {}).get("name") or "Unknown")
        categories = [str(category.get("name", "")).lower() for category in item.get("categories") or [] if isinstance(category, dict)]
        full_title = f"{title} at {company}"
        score = 72 if "intern" in title.lower() or "engineering" in categories else 58
        records.append(
            SignalRecord(
                id=f"themuse:{item.get('id', full_title)}",
                topic=infer_topic(" ".join(categories) if categories else title),
                title=full_title,
                source="The Muse",
                category="jobs",
                url=str((item.get("refs") or {}).get("landing_page") or ""),
                score=score,
                velocity=score,
                metadata={"categories": categories},
            )
        )
    return records


def parse_arbeitnow_jobs(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "data"):
        title = str(item.get("title") or "Arbeitnow job")
        company = str(item.get("company_name") or "Unknown")
        tags = [str(tag).lower() for tag in item.get("tags") or []]
        score = 72 if any(tag in {"ai", "python", "machine learning", "ml"} for tag in tags) else 57
        records.append(
            SignalRecord(
                id=f"arbeitnow:{item.get('slug', title)}",
                topic=infer_topic(" ".join(tags) if tags else title),
                title=f"{title} at {company}",
                source="Arbeitnow",
                category="jobs",
                url=str(item.get("url") or ""),
                score=score,
                velocity=score,
                metadata={"tags": tags},
            )
        )
    return records


def parse_codeforces_contests(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "result"):
        if str(item.get("phase", "")).upper() not in {"BEFORE", "CODING"}:
            continue
        title = str(item.get("name") or "Codeforces contest")
        starts_in = abs(_as_int(item.get("relativeTimeSeconds")))
        score = 75 if starts_in <= 7 * 24 * 3600 else 60
        records.append(
            SignalRecord(
                id=f"codeforces:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Codeforces",
                category="hackathons",
                url=f"https://codeforces.com/contest/{item.get('id', '')}",
                score=score,
                velocity=max(1, starts_in),
                metadata={"phase": item.get("phase"), "starts_in_seconds": starts_in},
            )
        )
    return records


def parse_openalex_works(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("display_name") or "OpenAlex work")
        citations = _as_int(item.get("cited_by_count"))
        institutions = []
        for authorship in item.get("authorships") or []:
            if isinstance(authorship, dict):
                institutions.extend(str(inst.get("display_name")) for inst in authorship.get("institutions") or [] if isinstance(inst, dict))
        records.append(
            SignalRecord(
                id=f"openalex:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="OpenAlex",
                category="research",
                url=str(item.get("id") or ""),
                score=min(62 + citations // 5, 100),
                velocity=citations,
                metadata={"citations": citations, "institutions": [name for name in institutions if name]},
            )
        )
    return records


def parse_wikipedia_pageviews(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items = _payload_list(payload, "items")
    if not items:
        return []
    article = str(items[-1].get("article") or "Wikipedia topic")
    total_views = sum(_as_int(item.get("views")) for item in items)
    return [
        SignalRecord(
            id=f"wikipedia:{article}",
            topic=infer_topic(article.replace("_", " ")),
            title=f"{article.replace('_', ' ')} pageview momentum",
            source="Wikipedia Pageviews",
            category="research",
            url=f"https://en.wikipedia.org/wiki/{article}",
            score=min(50 + total_views // 1000, 100),
            velocity=total_views,
            metadata={"days": len(items)},
        )
    ]


def parse_coingecko_trending(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for coin in _payload_list(payload, "coins"):
        item = coin.get("item", coin)
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("id") or "CoinGecko asset")
        rank_score = _as_int(item.get("score"))
        records.append(
            SignalRecord(
                id=f"coingecko:{item.get('id', name)}",
                topic=infer_topic(name),
                title=f"{name} ({str(item.get('symbol') or '').upper()}) trending on CoinGecko".strip(),
                source="CoinGecko",
                category="finance",
                url=f"https://www.coingecko.com/en/coins/{item.get('id', '')}",
                score=max(55, 85 - rank_score * 3),
                velocity=max(1, 20 - rank_score),
                metadata={"symbol": item.get("symbol"), "rank_score": rank_score},
            )
        )
    return records


def parse_itunes_results(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("trackName") or item.get("collectionName") or "App Store result")
        rating = float(item.get("averageUserRating") or 0)
        pain_bonus = 20 if 0 < rating < 3 else 0
        records.append(
            SignalRecord(
                id=f"itunes:{item.get('trackId', title)}",
                topic=infer_topic(title),
                title=title,
                source="iTunes App Store",
                category="app_stores",
                url=str(item.get("trackViewUrl") or ""),
                score=min(55 + pain_bonus + _as_int(item.get("userRatingCount")) // 100, 100),
                velocity=rating,
                metadata={"rating": rating, "ratings": item.get("userRatingCount")},
            )
        )
    return records


def parse_steam_featured(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items: list[dict[str, Any]] = []
    if isinstance(payload, dict):
        for key in ("large_capsules", "featured_win"):
            items.extend(_payload_list(payload, key))
        for section in ("top_sellers", "specials", "new_releases"):
            section_value = payload.get(section)
            if isinstance(section_value, dict):
                items.extend(_payload_list(section_value, "items"))
    else:
        items = _payload_list(payload, "items")

    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("name") or "Steam app")
        discount = _as_int(item.get("discount_percent"))
        records.append(
            SignalRecord(
                id=f"steam:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Steam",
                category="app_stores",
                url=f"https://store.steampowered.com/app/{item.get('id', '')}",
                score=min(55 + discount, 100),
                velocity=discount,
                metadata={"image": item.get("header_image")},
            )
        )
    return records


def parse_pypi_package(package: str, payload: dict[str, Any]) -> list[SignalRecord]:
    info = payload.get("info") or {}
    summary = str(info.get("summary") or "")
    return [
        SignalRecord(
            id=f"pypi:{package}",
            topic=infer_topic(package),
            title=f"{package} package signal",
            source="PyPI",
            category="code",
            url=str(info.get("package_url") or f"https://pypi.org/project/{package}/"),
            score=64,
            velocity=1,
            summary=summary[:280],
            metadata={"version": info.get("version")},
        )
    ]


def parse_npm_package(package: str, payload: dict[str, Any]) -> list[SignalRecord]:
    description = str(payload.get("description") or "")
    return [
        SignalRecord(
            id=f"npm:{package}",
            topic=infer_topic(package),
            title=f"{package} npm package signal",
            source="npm Registry",
            category="code",
            url=str(payload.get("homepage") or f"https://www.npmjs.com/package/{package}"),
            score=64,
            velocity=1,
            summary=description[:280],
            metadata={"version": (payload.get("dist-tags") or {}).get("latest")},
        )
    ]


def parse_yc_companies(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items = _payload_list(payload, "companies") or _payload_list(payload, "results") or _payload_list(payload, "data")
    records: list[SignalRecord] = []
    for item in items:
        name = str(item.get("name") or item.get("company") or "YC company")
        one_liner = str(item.get("one_liner") or item.get("description") or item.get("tagline") or "")
        industries = [str(industry) for industry in item.get("industries") or item.get("tags") or []]
        haystack = f"{name} {one_liner} {' '.join(industries)}".lower()
        score = 76 if any(term in haystack for term in ["ai", "agent", "developer", "automation"]) else 64
        records.append(
            SignalRecord(
                id=f"yc:{item.get('id', name)}",
                topic=infer_topic(" ".join(industries) if industries else name),
                title=f"{name} YC company signal",
                source="YC Companies",
                category="finance",
                url=str(item.get("url") or item.get("website") or "https://www.ycombinator.com/companies"),
                score=score,
                velocity=score,
                summary=one_liner[:280],
                metadata={"batch": item.get("batch"), "industries": industries},
            )
        )
    return records


def parse_sec_submissions(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    if not isinstance(payload, dict):
        return []
    company = str(payload.get("name") or payload.get("entityName") or "SEC company")
    cik = str(payload.get("cik") or payload.get("cik_str") or "").zfill(10)
    recent = ((payload.get("filings") or {}).get("recent") or {}) if isinstance(payload.get("filings"), dict) else {}
    forms = list(recent.get("form") or [])
    accessions = list(recent.get("accessionNumber") or [])
    dates = list(recent.get("filingDate") or [])
    records: list[SignalRecord] = []
    for index, form in enumerate(forms[:6]):
        form_name = str(form)
        accession = str(accessions[index]) if index < len(accessions) else f"{company}:{index}"
        filing_date = str(dates[index]) if index < len(dates) else ""
        score = 78 if form_name in {"10-K", "10-Q", "8-K", "S-1"} else 62
        records.append(
            SignalRecord(
                id=f"sec:{cik}:{accession}",
                topic=infer_topic(f"{company} {form_name}"),
                title=f"{company} filed {form_name}",
                source="SEC EDGAR",
                category="finance",
                url=f"https://www.sec.gov/edgar/browse/?CIK={cik.lstrip('0')}",
                score=score,
                velocity=score,
                summary=f"SEC filing {form_name} submitted {filing_date}".strip(),
                metadata={"cik": cik, "form": form_name, "accession": accession, "filing_date": filing_date},
            )
        )
    return records


def parse_duckduckgo_results(text: str) -> list[SignalRecord]:
    links = re.findall(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, flags=re.I | re.S)
    snippets = re.findall(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>', text, flags=re.I | re.S)
    snippet_texts = [_clean_html(next((part for part in pair if part), "")) for pair in snippets]
    records: list[SignalRecord] = []
    for index, (url, title_html) in enumerate(links[:8]):
        title = _clean_html(title_html)
        if not title:
            continue
        summary = snippet_texts[index] if index < len(snippet_texts) else ""
        records.append(
            SignalRecord(
                id=f"duckduckgo:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="DuckDuckGo",
                category="search",
                url=html.unescape(url),
                score=65 + min(index, 5),
                velocity=max(1, 8 - index),
                summary=summary[:280],
            )
        )
    return records


def parse_google_trends_rss(text: str) -> list[SignalRecord]:
    root = ET.fromstring(text)
    records: list[SignalRecord] = []
    for index, item in enumerate(root.findall(".//item")[:8]):
        title = (item.findtext("title") or "Google trend").strip()
        if not title:
            continue
        traffic = _traffic_to_int(_find_child_text(item, "approx_traffic"))
        news_url = _find_child_text(item, "news_item_url") or (item.findtext("link") or "")
        records.append(
            SignalRecord(
                id=f"google-trends:{index}:{title.lower()}",
                topic=infer_topic(title),
                title=f"{title} is trending on Google",
                source="Google Trends",
                category="search",
                url=news_url,
                score=min(62 + traffic // 50_000, 100) if traffic else 62,
                velocity=traffic,
                summary=_find_child_text(item, "news_item_title")[:280],
                metadata={"approx_traffic": traffic},
            )
        )
    return records


def parse_paperswithcode_results(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("title") or "Papers With Code paper")
        repositories = [repo for repo in item.get("repositories") or [] if isinstance(repo, dict)]
        repo_stars = max([_as_int(repo.get("stars")) for repo in repositories] or [0])
        records.append(
            SignalRecord(
                id=f"pwc:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Papers With Code",
                category="research",
                url=str(item.get("url_abs") or item.get("url") or "https://paperswithcode.com"),
                score=min(68 + repo_stars // 100, 100),
                velocity=max(1, repo_stars),
                summary=str(item.get("abstract") or "")[:280],
                metadata={"repo_stars": repo_stars},
            )
        )
    return records


def parse_libraries_io_project(package: str, payload: dict[str, Any]) -> list[SignalRecord]:
    name = str(payload.get("name") or package)
    dependents = _as_int(payload.get("dependent_repos_count") or payload.get("dependents_count"))
    stars = _as_int(payload.get("stars"))
    return [
        SignalRecord(
            id=f"libraries-io:{payload.get('platform', 'package')}:{name}",
            topic=infer_topic(name),
            title=f"{name} cross-language dependency signal",
            source="Libraries.io",
            category="code",
            url=str(payload.get("repository_url") or payload.get("package_url") or "https://libraries.io"),
            score=min(58 + dependents // 100 + stars // 500, 100),
            velocity=max(dependents, stars, 1),
            summary=str(payload.get("description") or "")[:280],
            metadata={"dependents": dependents, "stars": stars, "platform": payload.get("platform")},
        )
    ]


def parse_producthunt_posts(payload: dict[str, Any]) -> list[SignalRecord]:
    posts = (((payload.get("data") or {}).get("posts") or {}).get("edges") or [])
    records: list[SignalRecord] = []
    for edge in posts:
        node = edge.get("node", edge) if isinstance(edge, dict) else {}
        if not isinstance(node, dict):
            continue
        title = str(node.get("name") or "Product Hunt launch")
        votes = _as_int(node.get("votesCount"))
        comments = _as_int(node.get("commentsCount"))
        topics = [
            str(((topic_edge.get("node") or {}).get("name") or "")).strip()
            for topic_edge in (((node.get("topics") or {}).get("edges") or []))
            if isinstance(topic_edge, dict)
        ]
        records.append(
            SignalRecord(
                id=f"producthunt:{node.get('id', title)}",
                topic=infer_topic(" ".join(topics) if topics else title),
                title=f"{title} launched on Product Hunt",
                source="Product Hunt",
                category="news",
                url=str(node.get("url") or ""),
                score=min(55 + votes // 10 + comments, 100),
                velocity=votes + comments,
                summary=str(node.get("tagline") or "")[:280],
                metadata={"votes": votes, "comments": comments, "topics": [topic for topic in topics if topic]},
            )
        )
    return records


def parse_adzuna_jobs(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results"):
        title = str(item.get("title") or "Adzuna job")
        company = str((item.get("company") or {}).get("display_name") or "Unknown")
        location = str((item.get("location") or {}).get("display_name") or "")
        score = 76 if "intern" in title.lower() or "machine learning" in title.lower() else 62
        records.append(
            SignalRecord(
                id=f"adzuna:{item.get('id', title)}",
                topic=infer_topic(title),
                title=f"{title} at {company}",
                source="Adzuna",
                category="jobs",
                url=str(item.get("redirect_url") or ""),
                score=score,
                velocity=score,
                summary=str(item.get("description") or "")[:280],
                metadata={"company": company, "location": location, "created": item.get("created")},
            )
        )
    return records


def parse_hackerearth_challenges(payload: dict[str, Any] | list[dict[str, Any]]) -> list[SignalRecord]:
    items = _payload_list(payload, "challenges") or _payload_list(payload, "results") or _payload_list(payload, "data")
    records: list[SignalRecord] = []
    for item in items:
        title = str(item.get("title") or item.get("name") or "HackerEarth challenge")
        participants = _as_int(item.get("participants") or item.get("registrations"))
        records.append(
            SignalRecord(
                id=f"hackerearth:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="HackerEarth",
                category="hackathons",
                url=str(item.get("url") or item.get("challenge_url") or "https://www.hackerearth.com/challenges/"),
                score=min(60 + participants // 100, 100),
                velocity=max(participants, 1),
                metadata={"participants": participants, "starts_at": item.get("starts_at"), "ends_at": item.get("ends_at")},
            )
        )
    return records


def parse_semantic_scholar_papers(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "data"):
        title = str(item.get("title") or "Semantic Scholar paper")
        citations = _as_int(item.get("citationCount"))
        year = _as_int(item.get("year"))
        records.append(
            SignalRecord(
                id=f"semantic-scholar:{item.get('paperId', title)}",
                topic=infer_topic(title),
                title=title,
                source="Semantic Scholar",
                category="research",
                url=str(item.get("url") or ""),
                score=min(62 + citations // 10, 100),
                velocity=max(citations, 1),
                summary=str(item.get("abstract") or "")[:280],
                metadata={"citations": citations, "year": year},
            )
        )
    return records


def parse_crunchbase_funding(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for entity in _payload_list(payload, "entities"):
        properties = entity.get("properties", entity)
        if not isinstance(properties, dict):
            continue
        org = properties.get("funded_organization_identifier") or properties.get("organization_identifier") or {}
        company = str(org.get("value") if isinstance(org, dict) else org or "Crunchbase company")
        amount = _money_to_int(properties.get("money_raised") or properties.get("amount_raised"))
        round_type = str(properties.get("investment_type") or properties.get("funding_type") or "funding")
        records.append(
            SignalRecord(
                id=f"crunchbase:{entity.get('uuid', company)}",
                topic=infer_topic(company),
                title=f"{company} raised {round_type}",
                source="Crunchbase",
                category="finance",
                url=str(properties.get("web_path") or "https://www.crunchbase.com"),
                score=min(64 + amount // 5_000_000, 100) if amount else 64,
                velocity=amount,
                metadata={"amount": amount, "round": round_type, "announced_on": properties.get("announced_on")},
            )
        )
    return records


def parse_brave_search_results(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for index, item in enumerate(_payload_list(payload.get("web") if isinstance(payload.get("web"), dict) else payload, "results")):
        title = str(item.get("title") or "Brave Search result")
        records.append(
            SignalRecord(
                id=f"brave:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="Brave Search",
                category="search",
                url=str(item.get("url") or ""),
                score=64 + min(index, 5),
                velocity=max(1, 8 - index),
                summary=str(item.get("description") or "")[:280],
            )
        )
    return records


def parse_tavily_results(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    answer = str(payload.get("answer") or "")
    for index, item in enumerate(_payload_list(payload, "results")):
        title = str(item.get("title") or "Tavily result")
        score = float(item.get("score") or 0)
        records.append(
            SignalRecord(
                id=f"tavily:{index}:{title}",
                topic=infer_topic(title),
                title=title,
                source="Tavily",
                category="search",
                url=str(item.get("url") or ""),
                score=min(58 + int(score * 40), 100),
                velocity=score,
                summary=(str(item.get("content") or answer))[:280],
                metadata={"answer": answer[:280] if answer else ""},
            )
        )
    if not records and answer:
        records.append(
            SignalRecord(
                id=f"tavily:answer:{hashlib.sha1(answer.encode('utf-8')).hexdigest()[:12]}",
                topic=infer_topic(answer),
                title="Tavily answer signal",
                source="Tavily",
                category="search",
                score=62,
                velocity=1,
                summary=answer[:280],
            )
        )
    return records


def parse_crossref_works(payload: dict[str, Any]) -> list[SignalRecord]:
    items = _payload_list(payload.get("message") if isinstance(payload.get("message"), dict) else payload, "items")
    records: list[SignalRecord] = []
    for item in items[:10]:
        title_value = item.get("title") or []
        title = str(title_value[0] if isinstance(title_value, list) and title_value else title_value or "Crossref work")
        citations = _as_int(item.get("is-referenced-by-count"))
        records.append(
            SignalRecord(
                id=f"crossref:{item.get('DOI', title)}",
                topic=infer_topic(title),
                title=title,
                source="Crossref",
                category="research",
                url=str(item.get("URL") or f"https://doi.org/{item.get('DOI', '')}"),
                score=min(62 + citations // 10, 100),
                velocity=max(citations, 1),
                summary=str(item.get("abstract") or item.get("container-title") or "")[:280],
                metadata={"doi": item.get("DOI"), "citations": citations},
            )
        )
    return records


def parse_europepmc_results(payload: dict[str, Any]) -> list[SignalRecord]:
    result_list = payload.get("resultList") if isinstance(payload.get("resultList"), dict) else payload
    records: list[SignalRecord] = []
    for item in _payload_list(result_list, "result")[:10]:
        title = str(item.get("title") or "Europe PMC result")
        citations = _as_int(item.get("citedByCount"))
        url = _first_nested_url(item.get("fullTextUrlList")) or (f"https://doi.org/{item.get('doi')}" if item.get("doi") else "")
        records.append(
            SignalRecord(
                id=f"europepmc:{item.get('id', title)}",
                topic=infer_topic(title),
                title=title,
                source="Europe PMC",
                category="research",
                url=url,
                score=min(60 + citations // 5, 100),
                velocity=max(citations, 1),
                summary=str(item.get("abstractText") or item.get("journalTitle") or "")[:280],
                metadata={"citations": citations, "journal": item.get("journalTitle"), "year": item.get("pubYear")},
            )
        )
    return records


def parse_pubmed_esearch(payload: dict[str, Any]) -> list[SignalRecord]:
    result = payload.get("esearchresult") if isinstance(payload.get("esearchresult"), dict) else payload
    id_list = [str(item) for item in result.get("idlist", [])] if isinstance(result, dict) else []
    count = _as_int(result.get("count") if isinstance(result, dict) else 0)
    records: list[SignalRecord] = []
    for index, pubmed_id in enumerate(id_list[:10]):
        records.append(
            SignalRecord(
                id=f"pubmed:{pubmed_id}",
                topic="pubmed research",
                title=f"PubMed research result {pubmed_id}",
                source="PubMed",
                category="research",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                score=min(60 + count // 10, 100),
                velocity=max(count - index, 1),
                metadata={"pubmed_id": pubmed_id, "result_count": count},
            )
        )
    return records


def parse_biorxiv_papers(source_name: str, payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "collection")[:10]:
        title = str(item.get("title") or f"{source_name} preprint")
        records.append(
            SignalRecord(
                id=f"{source_name.lower()}:{item.get('doi', title)}",
                topic=infer_topic(title),
                title=title,
                source=source_name,
                category="research",
                url=f"https://doi.org/{item.get('doi')}" if item.get("doi") else str(item.get("server") or ""),
                score=68,
                velocity=1,
                summary=str(item.get("abstract") or "")[:280],
                metadata={"doi": item.get("doi"), "date": item.get("date"), "authors": item.get("authors")},
            )
        )
    return records


def parse_gdelt_articles(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for index, item in enumerate(_payload_list(payload, "articles")[:10]):
        title = str(item.get("title") or "GDELT article")
        records.append(
            SignalRecord(
                id=f"gdelt:{item.get('url', index)}",
                topic=infer_topic(title),
                title=title,
                source="GDELT",
                category="news",
                url=str(item.get("url") or ""),
                score=max(56, 70 - index),
                velocity=max(10 - index, 1),
                summary=str(item.get("seendate") or item.get("domain") or "")[:280],
                metadata={"domain": item.get("domain"), "seen_date": item.get("seendate"), "language": item.get("language")},
            )
        )
    return records


def parse_common_crawl_results(payload: list[dict[str, Any]] | str) -> list[SignalRecord]:
    if isinstance(payload, str):
        items = [json.loads(line) for line in payload.splitlines() if line.strip()]
    else:
        items = payload
    records: list[SignalRecord] = []
    for item in items[:10]:
        url = str(item.get("url") or "")
        if not url:
            continue
        records.append(
            SignalRecord(
                id=f"common-crawl:{item.get('digest', item.get('timestamp', url))}",
                topic=infer_topic(url.replace("https://", "").replace("http://", "")),
                title=f"Common Crawl captured {url}",
                source="Common Crawl",
                category="search",
                url=url,
                score=58,
                velocity=1,
                metadata={"timestamp": item.get("timestamp"), "mime": item.get("mime"), "status": item.get("status")},
            )
        )
    return records


def parse_greenhouse_jobs(payload: dict[str, Any], board: str) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "jobs")[:10]:
        title = str(item.get("title") or "Greenhouse job")
        location = item.get("location") or {}
        location_name = str(location.get("name") if isinstance(location, dict) else location or "")
        records.append(
            SignalRecord(
                id=f"greenhouse:{board}:{item.get('id', title)}",
                topic=infer_topic(title),
                title=f"{title} at {board}",
                source="Greenhouse Jobs",
                category="jobs",
                url=str(item.get("absolute_url") or ""),
                score=72 if any(term in title.lower() for term in ["ai", "machine learning", "agent", "intern"]) else 58,
                velocity=1,
                summary=location_name[:280],
                metadata={"board": board, "location": location_name, "updated_at": item.get("updated_at")},
            )
        )
    return records


def parse_lever_jobs(payload: list[dict[str, Any]] | dict[str, Any], company: str) -> list[SignalRecord]:
    items = payload if isinstance(payload, list) else _payload_list(payload, "postings")
    records: list[SignalRecord] = []
    for item in items[:10]:
        title = str(item.get("text") or item.get("title") or "Lever job")
        categories = item.get("categories") or {}
        location = str(categories.get("location") if isinstance(categories, dict) else "")
        records.append(
            SignalRecord(
                id=f"lever:{company}:{item.get('id', title)}",
                topic=infer_topic(title),
                title=f"{title} at {company}",
                source="Lever Jobs",
                category="jobs",
                url=str(item.get("hostedUrl") or item.get("applyUrl") or ""),
                score=72 if any(term in title.lower() for term in ["ai", "machine learning", "agent", "intern"]) else 58,
                velocity=1,
                summary=location[:280],
                metadata={"company": company, "location": location, "team": categories.get("team") if isinstance(categories, dict) else ""},
            )
        )
    return records


def parse_grantsgov_opportunities(payload: dict[str, Any]) -> list[SignalRecord]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    opportunities = _payload_list(data, "oppHits") or _payload_list(data, "opportunities")
    records: list[SignalRecord] = []
    for item in opportunities[:10]:
        title = str(item.get("title") or item.get("oppTitle") or "Grant opportunity")
        agency = str(item.get("agency") or item.get("agencyCode") or "")
        records.append(
            SignalRecord(
                id=f"grants-gov:{item.get('id', item.get('oppNum', title))}",
                topic=infer_topic(title),
                title=title,
                source="Grants.gov",
                category="finance",
                url=str(item.get("url") or "https://www.grants.gov/search-results-detail/" + str(item.get("id", ""))),
                score=72 if any(term in title.lower() for term in ["ai", "technology", "research", "innovation"]) else 60,
                velocity=1,
                summary=agency[:280],
                metadata={"agency": agency, "open_date": item.get("openDate"), "close_date": item.get("closeDate")},
            )
        )
    return records


def parse_usaspending_awards(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results")[:10]:
        award_id = str(item.get("Award ID") or item.get("generated_unique_award_id") or item.get("award_id") or "award")
        recipient = str(item.get("Recipient Name") or item.get("recipient_name") or "USAspending recipient")
        amount = _money_to_int(item.get("Award Amount") or item.get("award_amount") or item.get("total_obligation"))
        agency = str(item.get("Awarding Agency") or item.get("awarding_agency") or "")
        records.append(
            SignalRecord(
                id=f"usaspending:{award_id}",
                topic=infer_topic(recipient),
                title=f"{recipient} received public award",
                source="USAspending",
                category="finance",
                url="https://www.usaspending.gov/",
                score=min(60 + amount // 1_000_000, 100) if amount else 60,
                velocity=max(amount, 1),
                summary=agency[:280],
                metadata={"amount": amount, "agency": agency, "award_id": award_id},
            )
        )
    return records


def parse_dockerhub_repositories(payload: dict[str, Any]) -> list[SignalRecord]:
    records: list[SignalRecord] = []
    for item in _payload_list(payload, "results")[:10]:
        namespace = str(item.get("namespace") or item.get("user") or "library")
        name = str(item.get("name") or "docker image")
        pulls = _as_int(item.get("pull_count"))
        stars = _as_int(item.get("star_count"))
        records.append(
            SignalRecord(
                id=f"dockerhub:{namespace}/{name}",
                topic=infer_topic(name),
                title=f"{namespace}/{name} container image velocity",
                source="Docker Hub",
                category="code",
                url=f"https://hub.docker.com/r/{namespace}/{name}",
                score=min(58 + pulls // 100_000 + stars // 50, 100),
                velocity=max(pulls, stars, 1),
                summary=str(item.get("description") or "")[:280],
                metadata={"pulls": pulls, "stars": stars, "last_updated": item.get("last_updated")},
            )
        )
    return records


def parse_rubygems_results(payload: list[dict[str, Any]] | dict[str, Any]) -> list[SignalRecord]:
    items = payload if isinstance(payload, list) else _payload_list(payload, "gems")
    records: list[SignalRecord] = []
    for item in items[:10]:
        name = str(item.get("name") or "ruby gem")
        downloads = _as_int(item.get("downloads") or item.get("version_downloads"))
        records.append(
            SignalRecord(
                id=f"rubygems:{name}",
                topic=infer_topic(name),
                title=f"{name} Ruby gem velocity",
                source="RubyGems",
                category="code",
                url=str(item.get("project_uri") or f"https://rubygems.org/gems/{name}"),
                score=min(58 + downloads // 10_000, 100),
                velocity=max(downloads, 1),
                summary=str(item.get("info") or "")[:280],
                metadata={"downloads": downloads, "version": item.get("version")},
            )
        )
    return records


def parse_fdroid_index(payload: dict[str, Any]) -> list[SignalRecord]:
    packages = payload.get("packages", {}) if isinstance(payload, dict) else {}
    records: list[SignalRecord] = []
    for package_name, item in list(packages.items())[:10]:
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else item
        name = _localized_text(metadata.get("name"), str(package_name)) if isinstance(metadata, dict) else str(package_name)
        summary = _localized_text(metadata.get("summary"), "") if isinstance(metadata, dict) else ""
        versions = item.get("versions") if isinstance(item.get("versions"), dict) else {}
        version_count = len(versions)
        records.append(
            SignalRecord(
                id=f"fdroid:{package_name}",
                topic=infer_topic(f"{name} {summary}"),
                title=f"{name} F-Droid app signal",
                source="F-Droid",
                category="app_stores",
                url=f"https://f-droid.org/packages/{package_name}/",
                score=min(56 + version_count, 100),
                velocity=max(version_count, 1),
                summary=summary[:280],
                metadata={"package": package_name, "versions": version_count},
            )
        )
    return records


def _clean_html(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _localized_text(value: Any, default: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get("en-US") or value.get("en") or next(iter(value.values()), default))
    return str(value or default)


def _first_nested_url(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    urls = value.get("fullTextUrl")
    if isinstance(urls, list):
        for entry in urls:
            if isinstance(entry, dict) and entry.get("url"):
                return str(entry["url"])
    if isinstance(urls, dict) and urls.get("url"):
        return str(urls["url"])
    return ""


def _find_child_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if child.tag.rsplit("}", 1)[-1] == local_name and child.text:
            return " ".join(child.text.split())
    return ""


def _traffic_to_int(value: str) -> int:
    cleaned = value.upper().replace("+", "").replace(",", "").strip()
    if not cleaned:
        return 0
    multiplier = 1
    if cleaned.endswith("K"):
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith("M"):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    try:
        return int(float(cleaned) * multiplier)
    except ValueError:
        return 0


def _money_to_int(value: Any) -> int:
    if isinstance(value, dict):
        value = value.get("value") or value.get("amount") or value.get("usd")
    return _as_int(value)


class GitHubSearchCollector(HTTPCollector):
    def __init__(self, topic: str = "agentic ai", token: str | None = None) -> None:
        super().__init__(name="GitHub Search", category="code")
        self.topic = topic
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN", "")

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._request(
                self.http_get,
                "https://api.github.com/search/repositories",
                params={
                    "q": f"{self.topic} pushed:>2026-01-01",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": 8,
                },
                headers={"Authorization": f"Bearer {self.token}"} if self.token else None,
            )
            response.raise_for_status()
            data = response.json()
            return parse_github_repositories(list(data.get("items", [])))  # type: ignore[union-attr]
        except Exception:
            return sample_signals("code")


class GitHubTrendingCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="GitHub Trending", category="code")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://github.com/trending")
            records = parse_github_trending_html(text)
            return records or source_fallback("GitHub Trending", "code", "github trending", 78)
        except Exception:
            return source_fallback("GitHub Trending", "code", "github trending", 78)


class GitLabExploreCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="GitLab Explore", category="code")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://gitlab.com/api/v4/projects", search=self.query, order_by="star_count", sort="desc", per_page=10)
            records = parse_gitlab_projects(data if isinstance(data, (dict, list)) else [])
            return records or source_fallback("GitLab Explore", "code", "gitlab projects", 58)
        except Exception:
            return source_fallback("GitLab Explore", "code", "gitlab projects", 58)


class MCPServersDirectoryCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="MCP Servers Directory", category="code")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://raw.githubusercontent.com/modelcontextprotocol/servers/main/README.md")
            records = parse_mcp_servers_markdown(text)
            return records or source_fallback("MCP Servers Directory", "code", "mcp server catalog", 62)
        except Exception:
            return source_fallback("MCP Servers Directory", "code", "mcp server catalog", 62)


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


class HNAlgoliaCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents") -> None:
        super().__init__(name="HN Algolia", category="social")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://hn.algolia.com/api/v1/search", query=self.query, tags="story", hitsPerPage=10)
            hits = list(data.get("hits", [])) if isinstance(data, dict) else []
            records = parse_hn_algolia_hits(hits)
            return records or source_fallback("HN Algolia", "social", "hacker news search", 62)
        except Exception:
            return source_fallback("HN Algolia", "social", "hacker news search", 62)


class RedditJSONCollector(HTTPCollector):
    def __init__(self, subreddit: str | None = None, subreddits: list[str] | None = None) -> None:
        super().__init__(name="Reddit JSON", category="social")
        configured = subreddits or _reddit_subreddits_from_env()
        if subreddit:
            configured = [subreddit]
        self.subreddits = configured or DEFAULT_REDDIT_SUBREDDITS

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for subreddit in self.subreddits:
            try:
                data = self.get_json(f"https://www.reddit.com/r/{subreddit}/hot.json", limit=8)
                children = data.get("data", {}).get("children", [])  # type: ignore[union-attr]
                records.extend(parse_reddit_children(list(children)))
            except Exception:
                continue
        return records or sample_signals("social")


def verify_reddit_oauth(
    client_id: str | None = None,
    client_secret: str | None = None,
    http_post: HttpPost = requests.post,
    timeout: float = 8.0,
) -> dict[str, object]:
    resolved_client_id = client_id if client_id is not None else os.getenv("REDDIT_CLIENT_ID", "")
    resolved_client_secret = client_secret if client_secret is not None else os.getenv("REDDIT_CLIENT_SECRET", "")
    if not resolved_client_id or not resolved_client_secret:
        return {
            "configured": False,
            "valid": False,
            "detail": "missing REDDIT_CLIENT_ID or REDDIT_CLIENT_SECRET",
            "token_type": "",
        }
    try:
        response = http_post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(resolved_client_id, resolved_client_secret),
            headers={"User-Agent": "internet-radar-v2/0.1 by local-user"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token", ""))
        token_type = str(payload.get("token_type", ""))
        if token:
            return {
                "configured": True,
                "valid": True,
                "detail": "token acquired",
                "token_type": token_type,
            }
        return {
            "configured": True,
            "valid": False,
            "detail": "token response did not include access_token",
            "token_type": token_type,
        }
    except Exception as exc:
        return {
            "configured": True,
            "valid": False,
            "detail": f"token request failed: {exc.__class__.__name__}",
            "token_type": "",
        }


class RedditAPICollector(HTTPCollector):
    def __init__(
        self,
        subreddit: str = "LocalLLaMA",
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        super().__init__(name="Reddit API", category="social")
        self.subreddit = subreddit
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET", "")

    def collect(self) -> list[SignalRecord]:
        if not self.client_id or not self.client_secret:
            return keyed_source_fallback("Reddit API", "social", "reddit developer discussion", 58)
        try:
            token_response = self._post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
            )
            token_response.raise_for_status()
            token = str(token_response.json().get("access_token", ""))
            if not token:
                return keyed_source_fallback("Reddit API", "social", "reddit developer discussion", 58)
            response = self._request(
                self.http_get,
                f"https://oauth.reddit.com/r/{self.subreddit}/hot",
                params={"limit": 8},
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            children = response.json().get("data", {}).get("children", [])
            records = parse_reddit_children(list(children))
            for record in records:
                record.source = "Reddit API"
                record.id = f"reddit-api:{record.id}"
            return records or source_fallback("Reddit API", "social", "reddit developer discussion", 58)
        except Exception:
            return source_fallback("Reddit API", "social", "reddit developer discussion", 58)


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
            try:
                pypi_payload = self.get_json(f"https://pypi.org/pypi/{package}/json")
                if isinstance(pypi_payload, dict):
                    signals.extend(parse_pypi_package(package, pypi_payload))
            except Exception:
                signals.extend(sample_signals("code")[:1])
        for package in ["ollama", "playwright"]:
            try:
                npm_payload = self.get_json(f"https://registry.npmjs.org/{package}")
                if isinstance(npm_payload, dict):
                    signals.extend(parse_npm_package(package, npm_payload))
            except Exception:
                signals.extend(sample_signals("code")[:1])
        return signals


class PyPICollector(HTTPCollector):
    def __init__(self, packages: list[str] | None = None) -> None:
        super().__init__(name="PyPI", category="code")
        self.packages = packages or ["streamlit", "ollama", "playwright"]

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for package in self.packages:
            try:
                data = self.get_json(f"https://pypi.org/pypi/{package}/json")
                if isinstance(data, dict):
                    records.extend(parse_pypi_package(package, data))
            except Exception:
                continue
        return records or source_fallback("PyPI", "code", "python package velocity", 64)


class NPMRegistryCollector(HTTPCollector):
    def __init__(self, packages: list[str] | None = None) -> None:
        super().__init__(name="npm Registry", category="code")
        self.packages = packages or ["ollama", "playwright", "streamlit"]

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for package in self.packages:
            try:
                data = self.get_json(f"https://registry.npmjs.org/{package}")
                if isinstance(data, dict):
                    records.extend(parse_npm_package(package, data))
            except Exception:
                continue
        return records or source_fallback("npm Registry", "code", "npm package velocity", 64)


class CratesIOCollector(HTTPCollector):
    def __init__(self, query: str = "llm") -> None:
        super().__init__(name="crates.io", category="code")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://crates.io/api/v1/crates", q=self.query, sort="downloads", per_page=10)
            records = parse_crates_results(data if isinstance(data, dict) else {})
            return records or source_fallback("crates.io", "code", "rust package velocity", 58)
        except Exception:
            return source_fallback("crates.io", "code", "rust package velocity", 58)


class BlueskyCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents") -> None:
        super().__init__(name="Bluesky", category="social")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts", q=self.query, limit=20)
            records = parse_bluesky_posts(data if isinstance(data, dict) else {})
            return records or source_fallback("Bluesky", "social", "bluesky early adopter signals", 58)
        except Exception:
            return source_fallback("Bluesky", "social", "bluesky early adopter signals", 58)


class MastodonCollector(HTTPCollector):
    def __init__(self, instance: str = "mastodon.social") -> None:
        super().__init__(name="Mastodon", category="social")
        self.instance = instance

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(f"https://{self.instance}/api/v1/trends/statuses")
            records = parse_mastodon_statuses(list(data) if isinstance(data, list) else [])
            return records or source_fallback("Mastodon", "social", "mastodon developer signals", 58)
        except Exception:
            return source_fallback("Mastodon", "social", "mastodon developer signals", 58)


class RSSCollector(HTTPCollector):
    def __init__(self, config_path: str | Path = "config/rss_feeds.yaml", max_feeds: int = 24) -> None:
        super().__init__(name="Tech RSS", category="news")
        self.config_path = Path(config_path)
        self.max_feeds = max_feeds

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for feed in self._feeds()[: self.max_feeds]:
            try:
                text = self.get_text(str(feed["url"]))
                records.extend(parse_rss_entries(text, source_name=str(feed["name"])))
            except Exception:
                continue
        return records or source_fallback("Tech RSS", "news", "rss technology news", 58)

    def _feeds(self) -> list[dict[str, str]]:
        if not self.config_path.exists():
            return [{"name": "Hacker News", "url": "https://news.ycombinator.com/rss"}]
        data = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        feeds = data.get("feeds", []) if isinstance(data, dict) else []
        return [
            {"name": str(feed.get("name") or "Tech RSS"), "url": str(feed.get("url") or "")}
            for feed in feeds
            if isinstance(feed, dict) and feed.get("url")
        ]


class ConfiguredRSSCollector(HTTPCollector):
    def __init__(
        self,
        name: str,
        category: str,
        topic: str,
        score: int,
        config_path: str | Path = "config/rss_feeds.yaml",
        max_feeds: int = 24,
    ) -> None:
        super().__init__(name=name, category=category)
        self.topic = topic
        self.score = score
        self.config_path = Path(config_path)
        self.max_feeds = max_feeds

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for feed in RSSCollector(self.config_path, max_feeds=self.max_feeds)._feeds()[: self.max_feeds]:
            try:
                text = self.get_text(str(feed["url"]))
                records.extend(parse_rss_entries(text, source_name=self.name))
            except Exception:
                continue
        return records or source_fallback(self.name, self.category, self.topic, self.score)


class HashnodeCollector(HTTPCollector):
    query = """
    query {
      storiesFeed(type: FEATURED, first: 20) {
        edges {
          node {
            id
            title
            brief
            url
            reactionCount
            responseCount
            tags { name }
          }
        }
      }
    }
    """

    def __init__(self, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="Hashnode", category="news")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._post("https://gql.hashnode.com", json={"query": self.query})
            response.raise_for_status()
            records = parse_hashnode_posts(response.json())
            return records or source_fallback("Hashnode", "news", "hashnode developer articles", 55)
        except Exception:
            return source_fallback("Hashnode", "news", "hashnode developer articles", 55)


class TLDRNewsletterCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="TLDR Newsletter", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://tldr.tech")
            records = parse_tldr_html(text)
            return records or source_fallback("TLDR Newsletter", "news", "tech newsletter signals", 55)
        except Exception:
            return source_fallback("TLDR Newsletter", "news", "tech newsletter signals", 55)


class IndieHackersRSSCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Indie Hackers", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://www.indiehackers.com/feed")
            records = parse_rss_entries(text, source_name="Indie Hackers")
            return records or source_fallback("Indie Hackers", "news", "indie hackers discussions", 55)
        except Exception:
            return source_fallback("Indie Hackers", "news", "indie hackers discussions", 55)


class CompanyEngineeringBlogsCollector(ConfiguredRSSCollector):
    def __init__(self) -> None:
        super().__init__(name="Company Engineering Blogs", category="news", topic="engineering blog signals", score=55, max_feeds=12)


class MLHCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="MLH", category="hackathons")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://mlh.io/seasons/2026/events")
            records = parse_mlh_events_html(text)
            return records or source_fallback("MLH", "hackathons", "mlh hackathons", 65)
        except Exception:
            return source_fallback("MLH", "hackathons", "mlh hackathons", 65)


class LeetCodeContestsCollector(HTTPCollector):
    query = """
    query {
      allContests {
        title
        titleSlug
        startTime
        duration
      }
    }
    """

    def __init__(self, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="LeetCode Contests", category="hackathons")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._post("https://leetcode.com/graphql", json={"query": self.query})
            response.raise_for_status()
            records = parse_leetcode_contests(response.json())
            return records or source_fallback("LeetCode Contests", "hackathons", "leetcode contests", 60)
        except Exception:
            return source_fallback("LeetCode Contests", "hackathons", "leetcode contests", 60)


class DevpostCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Devpost", category="hackathons")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://devpost.com/hackathons")
            records = parse_devpost_hackathons_html(text)
            return records or source_fallback("Devpost", "hackathons", "devpost hackathons", 70)
        except Exception:
            return source_fallback("Devpost", "hackathons", "devpost hackathons", 70)


class LobstersCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Lobsters", category="news")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://lobste.rs/hottest.json")
            return parse_lobsters_stories(list(data))  # type: ignore[arg-type]
        except Exception:
            return sample_signals("news")


class TheMuseCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="The Muse", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.themuse.com/api/public/jobs", page=1, category="Computer and IT")
            return parse_themuse_jobs(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("jobs")


class YCJobsCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="YC Jobs", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://www.ycombinator.com/jobs")
            records = parse_yc_jobs_html(text)
            return records or source_fallback("YC Jobs", "jobs", "yc startup jobs", 60)
        except Exception:
            return source_fallback("YC Jobs", "jobs", "yc startup jobs", 60)


class ArbeitnowCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Arbeitnow", category="jobs")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.arbeitnow.com/api/job-board-api")
            return parse_arbeitnow_jobs(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("jobs")


class CodeforcesCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Codeforces", category="hackathons")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://codeforces.com/api/contest.list")
            return parse_codeforces_contests(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("hackathons")


class OpenAlexCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="OpenAlex", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://api.openalex.org/works", search=self.query, per_page=8, sort="cited_by_count:desc")
            return parse_openalex_works(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class StackOverflowCollector(HTTPCollector):
    def __init__(self, tagged: str = "python;ai") -> None:
        super().__init__(name="Stack Overflow", category="social")
        self.tagged = tagged

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(
                "https://api.stackexchange.com/2.3/questions",
                order="desc",
                sort="activity",
                tagged=self.tagged,
                site="stackoverflow",
                pagesize=10,
            )
            records = parse_stackoverflow_questions(data if isinstance(data, dict) else {})
            return records or source_fallback("Stack Overflow", "social", "stackoverflow questions", 58)
        except Exception:
            return source_fallback("Stack Overflow", "social", "stackoverflow questions", 58)


class HuggingFaceModelsCollector(HTTPCollector):
    def __init__(self, query: str = "agents") -> None:
        super().__init__(name="Hugging Face Models", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://huggingface.co/api/models", search=self.query, sort="downloads", direction=-1, limit=10)
            records = parse_huggingface_models(data if isinstance(data, (dict, list)) else [])
            return records or source_fallback("Hugging Face Models", "research", "hugging face models", 62)
        except Exception:
            return source_fallback("Hugging Face Models", "research", "hugging face models", 62)


class HuggingFacePapersCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Hugging Face Papers", category="research")

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://huggingface.co/papers/rss")
            records = parse_rss_entries(text, source_name="Hugging Face Papers")
            return records or source_fallback("Hugging Face Papers", "research", "hugging face papers", 62)
        except Exception:
            return source_fallback("Hugging Face Papers", "research", "hugging face papers", 62)


class ConferenceRSSCollector(ConfiguredRSSCollector):
    def __init__(self) -> None:
        super().__init__(name="Conference RSS", category="research", topic="conference research signals", score=58, max_feeds=12)


class WikipediaPageviewsCollector(HTTPCollector):
    def __init__(self, article: str = "Large_language_model") -> None:
        super().__init__(name="Wikipedia Pageviews", category="research")
        self.article = article

    def collect(self) -> list[SignalRecord]:
        end = datetime.now(UTC) - timedelta(days=1)
        start = end - timedelta(days=6)
        try:
            data = self.get_json(
                f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{self.article}/daily/{start:%Y%m%d}/{end:%Y%m%d}"
            )
            return parse_wikipedia_pageviews(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class CoinGeckoCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="CoinGecko", category="finance")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://api.coingecko.com/api/v3/search/trending")
            return parse_coingecko_trending(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("finance")


class YahooFinanceCollector(HTTPCollector):
    def __init__(self, symbols: str = "NVDA,MSFT,AMD") -> None:
        super().__init__(name="Yahoo Finance", category="finance")
        self.symbols = symbols

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://query1.finance.yahoo.com/v7/finance/quote", symbols=self.symbols)
            records = parse_yahoo_quote(data if isinstance(data, dict) else {})
            return records or source_fallback("Yahoo Finance", "finance", "stock trends", 60)
        except Exception:
            return source_fallback("Yahoo Finance", "finance", "stock trends", 60)


class OpenCollectiveCollector(HTTPCollector):
    query = """
    query {
      search(term: "AI", limit: 10) {
        nodes {
          id
          slug
          name
          type
          description
          stats { totalAmountReceived { value } }
        }
      }
    }
    """

    def __init__(self, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="OpenCollective", category="finance")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._post("https://api.opencollective.com/graphql/v2", json={"query": self.query})
            response.raise_for_status()
            records = parse_opencollective_search(response.json())
            return records or source_fallback("OpenCollective", "finance", "open source funding", 60)
        except Exception:
            return source_fallback("OpenCollective", "finance", "open source funding", 60)


class ITunesCollector(HTTPCollector):
    def __init__(self, term: str = "AI assistant") -> None:
        super().__init__(name="iTunes App Store", category="app_stores")
        self.term = term

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://itunes.apple.com/search", term=self.term, entity="software", limit=8)
            return parse_itunes_results(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("app_stores")


class GooglePlayCollector(HTTPCollector):
    def __init__(self, term: str = "AI assistant") -> None:
        super().__init__(name="Google Play", category="app_stores")
        self.term = term

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://play.google.com/store/search", q=self.term, c="apps", hl="en", gl="US")
            records = parse_playstore_search_html(text)
            return records or source_fallback("Google Play", "app_stores", "google play reviews", 58)
        except Exception:
            return source_fallback("Google Play", "app_stores", "google play reviews", 58)


class SteamCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="Steam", category="app_stores")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://store.steampowered.com/api/featuredcategories")
            return parse_steam_featured(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("app_stores")


class DuckDuckGoCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents startup pain") -> None:
        super().__init__(name="DuckDuckGo", category="search")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://duckduckgo.com/html/", q=self.query)
            records = parse_duckduckgo_results(text)
            return records or sample_signals("search")
        except Exception:
            return sample_signals("search")


class GoogleTrendsCollector(HTTPCollector):
    def __init__(self, geo: str = "US") -> None:
        super().__init__(name="Google Trends", category="search")
        self.geo = geo

    def collect(self) -> list[SignalRecord]:
        try:
            text = self.get_text("https://trends.google.com/trending/rss", geo=self.geo)
            records = parse_google_trends_rss(text)
            return records or google_trends_fallback()
        except Exception:
            return google_trends_fallback()


class WaybackCollector(HTTPCollector):
    def __init__(self, target_url: str = "https://openai.com") -> None:
        super().__init__(name="Wayback Machine", category="search")
        self.target_url = target_url

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://archive.org/wayback/available", url=self.target_url)
            records = parse_wayback_available(data if isinstance(data, dict) else {}, self.target_url)
            return records or source_fallback("Wayback Machine", "search", "web archive changes", 55)
        except Exception:
            return source_fallback("Wayback Machine", "search", "web archive changes", 55)


class YCCompaniesCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="YC Companies", category="finance")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.ycombinator.com/companies.json")
            return parse_yc_companies(data if isinstance(data, (dict, list)) else [])
        except Exception:
            return sample_signals("finance")


class SECEdgarCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="SEC EDGAR", category="finance")

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for cik in ["0001045810", "0000789019"]:
            try:
                data = self.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
                records.extend(parse_sec_submissions(data if isinstance(data, dict) else {}))
            except Exception:
                records.extend(sample_signals("finance")[:1])
        return records


class PapersWithCodeCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="Papers With Code", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://paperswithcode.com/api/v1/papers/", q=self.query)
            return parse_paperswithcode_results(data if isinstance(data, dict) else [])
        except Exception:
            return sample_signals("research")


class CrossrefCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="Crossref", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://api.crossref.org/works", query=self.query, rows=8, sort="published", order="desc")
            records = parse_crossref_works(data if isinstance(data, dict) else {})
            return records or source_fallback("Crossref", "research", "crossref research metadata", 62)
        except Exception:
            return source_fallback("Crossref", "research", "crossref research metadata", 62)


class EuropePMCCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="Europe PMC", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://www.ebi.ac.uk/europepmc/webservices/rest/search", query=self.query, format="json", pageSize=8)
            records = parse_europepmc_results(data if isinstance(data, dict) else {})
            return records or source_fallback("Europe PMC", "research", "europe pmc research", 62)
        except Exception:
            return source_fallback("Europe PMC", "research", "europe pmc research", 62)


class PubMedCollector(HTTPCollector):
    def __init__(self, query: str = "agentic ai") -> None:
        super().__init__(name="PubMed", category="research")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(
                "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                db="pubmed",
                term=self.query,
                retmode="json",
                retmax=8,
                sort="date",
            )
            records = parse_pubmed_esearch(data if isinstance(data, dict) else {})
            return records or source_fallback("PubMed", "research", "pubmed research", 62)
        except Exception:
            return source_fallback("PubMed", "research", "pubmed research", 62)


class BioRxivCollector(HTTPCollector):
    def __init__(self, server: str = "biorxiv") -> None:
        super().__init__(name="bioRxiv" if server == "biorxiv" else "medRxiv", category="research")
        self.server = server

    def collect(self) -> list[SignalRecord]:
        end = datetime.now(UTC)
        start = end - timedelta(days=14)
        try:
            data = self.get_json(f"https://api.biorxiv.org/details/{self.server}/{start:%Y-%m-%d}/{end:%Y-%m-%d}/0")
            records = parse_biorxiv_papers(self.name, data if isinstance(data, dict) else {})
            return records or source_fallback(self.name, "research", f"{self.name.lower()} preprints", 64)
        except Exception:
            return source_fallback(self.name, "research", f"{self.name.lower()} preprints", 64)


class GDELTCollector(HTTPCollector):
    def __init__(self, query: str = "artificial intelligence") -> None:
        super().__init__(name="GDELT", category="news")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                query=self.query,
                mode="ArtList",
                format="json",
                maxrecords=10,
                sort="HybridRel",
            )
            records = parse_gdelt_articles(data if isinstance(data, dict) else {})
            return records or source_fallback("GDELT", "news", "global news signals", 62)
        except Exception:
            return source_fallback("GDELT", "news", "global news signals", 62)


class CommonCrawlCollector(HTTPCollector):
    def __init__(self, target: str = "openai.com/*") -> None:
        super().__init__(name="Common Crawl", category="search")
        self.target = target

    def collect(self) -> list[SignalRecord]:
        try:
            collections = self.get_json("https://index.commoncrawl.org/collinfo.json")
            collection_id = str((collections[0] if isinstance(collections, list) and collections else {}).get("id", "CC-MAIN-2026-18"))
            response = self._request(
                self.http_get,
                f"https://index.commoncrawl.org/{collection_id}-index",
                params={"url": self.target, "output": "json", "limit": 10},
            )
            response.raise_for_status()
            text = str(response.text)
            records = parse_common_crawl_results(text)
            return records or source_fallback("Common Crawl", "search", "web crawl index", 58)
        except Exception:
            return source_fallback("Common Crawl", "search", "web crawl index", 58)


class GreenhouseJobsCollector(HTTPCollector):
    def __init__(self, boards: list[str] | None = None) -> None:
        super().__init__(name="Greenhouse Jobs", category="jobs")
        self.boards = boards or ["databricks", "stripe"]

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for board in self.boards:
            try:
                data = self.get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", content="true")
                if isinstance(data, dict):
                    records.extend(parse_greenhouse_jobs(data, board=board))
            except Exception:
                continue
        return records or source_fallback("Greenhouse Jobs", "jobs", "greenhouse public jobs", 58)


class LeverJobsCollector(HTTPCollector):
    def __init__(self, companies: list[str] | None = None) -> None:
        super().__init__(name="Lever Jobs", category="jobs")
        self.companies = companies or ["spotify", "coupa", "Onehouse", "arcadia"]

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for company in self.companies:
            try:
                data = self.get_json(f"https://api.lever.co/v0/postings/{company}", mode="json")
                if isinstance(data, (dict, list)):
                    records.extend(parse_lever_jobs(data, company=company))
            except Exception:
                continue
        return records or source_fallback("Lever Jobs", "jobs", "lever public jobs", 58)


class GrantsGovCollector(HTTPCollector):
    def __init__(self, keyword: str = "artificial intelligence", http_post: HttpPost = requests.post) -> None:
        super().__init__(name="Grants.gov", category="finance")
        self.keyword = keyword
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._post(
                "https://api.grants.gov/v1/api/search2",
                json={"keyword": self.keyword, "rows": 10, "oppStatuses": "forecasted|posted"},
            )
            response.raise_for_status()
            records = parse_grantsgov_opportunities(response.json())
            return records or source_fallback("Grants.gov", "finance", "grant opportunities", 62)
        except Exception:
            return source_fallback("Grants.gov", "finance", "grant opportunities", 62)


class USASpendingCollector(HTTPCollector):
    def __init__(self, keyword: str = "artificial intelligence", http_post: HttpPost = requests.post) -> None:
        super().__init__(name="USAspending", category="finance")
        self.keyword = keyword
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        try:
            response = self._post(
                "https://api.usaspending.gov/api/v2/search/spending_by_award/",
                json={
                    "filters": {"keywords": [self.keyword], "award_type_codes": ["A", "B", "C", "D"]},
                    "fields": ["Award ID", "Recipient Name", "Award Amount", "Awarding Agency"],
                    "page": 1,
                    "limit": 10,
                    "sort": "Award Amount",
                    "order": "desc",
                },
            )
            response.raise_for_status()
            records = parse_usaspending_awards(response.json())
            return records or source_fallback("USAspending", "finance", "public spending awards", 62)
        except Exception:
            return source_fallback("USAspending", "finance", "public spending awards", 62)


class DockerHubCollector(HTTPCollector):
    def __init__(self, query: str = "ai agent") -> None:
        super().__init__(name="Docker Hub", category="code")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://hub.docker.com/v2/search/repositories/", query=self.query, page_size=10)
            records = parse_dockerhub_repositories(data if isinstance(data, dict) else {})
            return records or source_fallback("Docker Hub", "code", "container image velocity", 58)
        except Exception:
            return source_fallback("Docker Hub", "code", "container image velocity", 58)


class RubyGemsCollector(HTTPCollector):
    def __init__(self, query: str = "ai") -> None:
        super().__init__(name="RubyGems", category="code")
        self.query = query

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://rubygems.org/api/v1/search.json", query=self.query)
            records = parse_rubygems_results(data if isinstance(data, (dict, list)) else [])
            return records or source_fallback("RubyGems", "code", "ruby package velocity", 58)
        except Exception:
            return source_fallback("RubyGems", "code", "ruby package velocity", 58)


class FDroidCollector(HTTPCollector):
    def __init__(self) -> None:
        super().__init__(name="F-Droid", category="app_stores")

    def collect(self) -> list[SignalRecord]:
        try:
            data = self.get_json("https://f-droid.org/repo/index-v2.json")
            records = parse_fdroid_index(data if isinstance(data, dict) else {})
            return records or source_fallback("F-Droid", "app_stores", "open source android apps", 56)
        except Exception:
            return source_fallback("F-Droid", "app_stores", "open source android apps", 56)


class LibrariesIOCollector(HTTPCollector):
    def __init__(self, package: str = "streamlit", platform: str = "pypi", api_key: str | None = None) -> None:
        super().__init__(name="Libraries.io", category="code")
        self.package = package
        self.platform = platform
        self.api_key = api_key or os.getenv("LIBRARIES_IO_API_KEY", "")

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("Libraries.io", "code", "cross language dependencies", 58)
        try:
            data = self.get_json(f"https://libraries.io/api/{self.platform}/{self.package}", api_key=self.api_key)
            return parse_libraries_io_project(self.package, data if isinstance(data, dict) else {})
        except Exception:
            return keyed_source_fallback("Libraries.io", "code", "cross language dependencies", 58)


class ProductHuntCollector(HTTPCollector):
    query = """
    query {
      posts(order: VOTES, first: 20) {
        edges {
          node {
            id
            name
            tagline
            votesCount
            commentsCount
            url
            topics { edges { node { name } } }
          }
        }
      }
    }
    """

    def __init__(self, token: str | None = None, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="Product Hunt", category="news")
        self.token = token or os.getenv("PRODUCTHUNT_TOKEN", "")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        if not self.token:
            return keyed_source_fallback("Product Hunt", "news", "product launches", 55)
        try:
            response = self._post(
                "https://api.producthunt.com/v2/api/graphql",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"query": self.query},
            )
            response.raise_for_status()
            return parse_producthunt_posts(response.json())
        except Exception:
            return keyed_source_fallback("Product Hunt", "news", "product launches", 55)


class AdzunaCollector(HTTPCollector):
    def __init__(self, query: str = "machine learning intern", country: str = "us", app_id: str | None = None, app_key: str | None = None) -> None:
        super().__init__(name="Adzuna", category="jobs")
        self.query = query
        self.country = country
        self.app_id = app_id or os.getenv("ADZUNA_APP_ID", "")
        self.app_key = app_key or os.getenv("ADZUNA_APP_KEY", "")

    def collect(self) -> list[SignalRecord]:
        if not self.app_id or not self.app_key:
            return keyed_source_fallback("Adzuna", "jobs", "adzuna jobs", 57)
        try:
            data = self.get_json(
                f"https://api.adzuna.com/v1/api/jobs/{self.country}/search/1",
                app_id=self.app_id,
                app_key=self.app_key,
                what=self.query,
                sort_by="date",
                results_per_page=50,
            )
            return parse_adzuna_jobs(data if isinstance(data, dict) else {})
        except Exception:
            return keyed_source_fallback("Adzuna", "jobs", "adzuna jobs", 57)


class HackerEarthCollector(HTTPCollector):
    def __init__(self, api_key: str | None = None) -> None:
        super().__init__(name="HackerEarth", category="hackathons")
        self.api_key = api_key or os.getenv("HACKEREARTH_API_KEY", "")

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("HackerEarth", "hackathons", "hackerearth challenges", 60)
        try:
            data = self.get_json("https://www.hackerearth.com/chrome-extension/events/api/events/", api_key=self.api_key)
            return parse_hackerearth_challenges(data if isinstance(data, (dict, list)) else {})
        except Exception:
            return keyed_source_fallback("HackerEarth", "hackathons", "hackerearth challenges", 60)


class SemanticScholarCollector(HTTPCollector):
    def __init__(self, query: str = "agentic browser automation", api_key: str | None = None) -> None:
        super().__init__(name="Semantic Scholar", category="research")
        self.query = query
        self.api_key = api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("Semantic Scholar", "research", "semantic scholar papers", 62)
        try:
            response = self._request(
                self.http_get,
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": self.query,
                    "limit": 20,
                    "fields": "title,abstract,url,citationCount,year",
                },
                headers={"x-api-key": self.api_key},
            )
            response.raise_for_status()
            return parse_semantic_scholar_papers(response.json())
        except Exception:
            return keyed_source_fallback("Semantic Scholar", "research", "semantic scholar papers", 62)


class CrunchbaseCollector(HTTPCollector):
    def __init__(self, api_key: str | None = None, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="Crunchbase", category="finance")
        self.api_key = api_key or os.getenv("CRUNCHBASE_API_KEY", "")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("Crunchbase", "finance", "funding rounds", 64)
        try:
            response = self._post(
                "https://api.crunchbase.com/api/v4/searches/funding_rounds",
                headers={"X-cb-user-key": self.api_key},
                json={
                    "field_ids": ["funded_organization_identifier", "money_raised", "announced_on", "investment_type"],
                    "order": [{"field_id": "announced_on", "sort": "desc"}],
                    "limit": 20,
                },
            )
            response.raise_for_status()
            return parse_crunchbase_funding(response.json())
        except Exception:
            return keyed_source_fallback("Crunchbase", "finance", "funding rounds", 64)


class BraveSearchCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents startup pain", api_key: str | None = None) -> None:
        super().__init__(name="Brave Search", category="search")
        self.query = query
        self.api_key = api_key or os.getenv("BRAVE_SEARCH_API_KEY", "")

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("Brave Search", "search", "brave search intelligence", 58)
        try:
            response = self._request(
                self.http_get,
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": self.query, "count": 10},
                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            )
            response.raise_for_status()
            return parse_brave_search_results(response.json())
        except Exception:
            return keyed_source_fallback("Brave Search", "search", "brave search intelligence", 58)


class TavilyCollector(HTTPCollector):
    def __init__(self, query: str = "browser agents startup pain", api_key: str | None = None, http_post: HttpPost = requests.post) -> None:
        super().__init__(name="Tavily", category="search")
        self.query = query
        self.api_key = api_key or os.getenv("TAVILY_API_KEY", "")
        self.http_post = http_post

    def collect(self) -> list[SignalRecord]:
        if not self.api_key:
            return keyed_source_fallback("Tavily", "search", "ai search intelligence", 58)
        try:
            response = self._post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": self.query,
                    "search_depth": "advanced",
                    "include_answer": True,
                    "max_results": 10,
                },
            )
            response.raise_for_status()
            return parse_tavily_results(response.json())
        except Exception:
            return keyed_source_fallback("Tavily", "search", "ai search intelligence", 58)


class SpecialIntelligenceCollector:
    name = "Special Intelligence"
    category = "mixed"

    def collect(self) -> list[SignalRecord]:
        return build_special_signals()


def default_collectors(use_live_network: bool = True) -> list[object]:
    if not use_live_network:
        return [SampleCollector()]
    return [
        GitHubSearchCollector(),
        GitHubTrendingCollector(),
        GitLabExploreCollector(),
        MCPServersDirectoryCollector(),
        HackerNewsCollector(),
        HNAlgoliaCollector(),
        RedditJSONCollector(),
        BlueskyCollector(),
        MastodonCollector(),
        StackOverflowCollector(),
        DevToCollector(),
        RSSCollector(),
        HashnodeCollector(),
        TLDRNewsletterCollector(),
        LobstersCollector(),
        IndieHackersRSSCollector(),
        CompanyEngineeringBlogsCollector(),
        RemoteOKCollector(),
        TheMuseCollector(),
        YCJobsCollector(),
        ArbeitnowCollector(),
        CodeforcesCollector(),
        DevpostCollector(),
        MLHCollector(),
        LeetCodeContestsCollector(),
        ArxivCollector(),
        OpenAlexCollector(),
        HuggingFaceModelsCollector(),
        HuggingFacePapersCollector(),
        ConferenceRSSCollector(),
        WikipediaPageviewsCollector(),
        CrossrefCollector(),
        EuropePMCCollector(),
        PubMedCollector(),
        BioRxivCollector("biorxiv"),
        BioRxivCollector("medrxiv"),
        CoinGeckoCollector(),
        YahooFinanceCollector(),
        OpenCollectiveCollector(),
        GrantsGovCollector(),
        USASpendingCollector(),
        ITunesCollector(),
        GooglePlayCollector(),
        SteamCollector(),
        FDroidCollector(),
        DuckDuckGoCollector(),
        WaybackCollector(),
        CommonCrawlCollector(),
        GoogleTrendsCollector(),
        GDELTCollector(),
        YCCompaniesCollector(),
        SECEdgarCollector(),
        PapersWithCodeCollector(),
        PyPICollector(),
        NPMRegistryCollector(),
        PackageCollector(),
        CratesIOCollector(),
        DockerHubCollector(),
        RubyGemsCollector(),
        GreenhouseJobsCollector(),
        LeverJobsCollector(),
        FocusedWebCrawlerCollector(),
        *_keyed_collectors_from_env(),
        SpecialIntelligenceCollector(),
    ]


class SampleCollector:
    name = "Sample Radar"
    category = "mixed"

    def collect(self) -> list[SignalRecord]:
        records: list[SignalRecord] = []
        for category in ["code", "social", "news", "jobs", "hackathons", "research", "finance", "app_stores"]:
            records.extend(sample_signals(category))
        records.extend(build_special_signals())
        return records


def google_trends_fallback() -> list[SignalRecord]:
    return [
        SignalRecord(
            id="sample:search:google-trends",
            topic="browser agents",
            title="browser agents is rising on Google Trends",
            source="Google Trends",
            category="search",
            url="https://trends.google.com/trends/explore?q=browser%20agents",
            score=68,
            velocity=50_000,
            metadata={"approx_traffic": 50_000},
        )
    ]


def source_fallback(name: str, category: str, topic: str, score: int) -> list[SignalRecord]:
    return [
        SignalRecord(
            id=f"source-fallback:{name.lower().replace(' ', '-').replace('.', '')}",
            topic=topic,
            title=f"{name} fallback signal",
            source=name,
            category=category,  # type: ignore[arg-type]
            score=score,
            velocity=max(score - 50, 1),
            summary=f"Deterministic fallback for {name} live collection.",
            metadata={"fallback": True},
        )
    ]


def keyed_source_fallback(name: str, category: str, topic: str, score: int) -> list[SignalRecord]:
    return [
        SignalRecord(
            id=f"keyed-fallback:{name.lower().replace(' ', '-').replace('.', '')}",
            topic=topic,
            title=f"{name} keyed-source fallback signal",
            source=name,
            category=category,  # type: ignore[arg-type]
            score=score,
            velocity=max(score - 50, 1),
            summary=f"Set the {name} API key in .env to enable live {name} collection.",
            metadata={"requires_api_key": True},
        )
    ]


def _keyed_collectors_from_env() -> list[object]:
    collectors: list[object] = []
    free_only = os.getenv("INTERNET_RADAR_FREE_ONLY", "0") == "1"
    if os.getenv("REDDIT_CLIENT_ID") and os.getenv("REDDIT_CLIENT_SECRET"):
        collectors.append(RedditAPICollector())
    if os.getenv("LIBRARIES_IO_API_KEY"):
        collectors.append(LibrariesIOCollector())
    if os.getenv("PRODUCTHUNT_TOKEN"):
        collectors.append(ProductHuntCollector())
    if os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_APP_KEY"):
        collectors.append(AdzunaCollector())
    if os.getenv("HACKEREARTH_API_KEY"):
        collectors.append(HackerEarthCollector())
    if os.getenv("SEMANTIC_SCHOLAR_API_KEY"):
        collectors.append(SemanticScholarCollector())
    if os.getenv("CRUNCHBASE_API_KEY") and not free_only:
        collectors.append(CrunchbaseCollector())
    if os.getenv("BRAVE_SEARCH_API_KEY") and not free_only:
        collectors.append(BraveSearchCollector())
    if os.getenv("TAVILY_API_KEY"):
        collectors.append(TavilyCollector())
    return collectors


def _reddit_subreddits_from_env() -> list[str]:
    configured = os.getenv("INTERNET_RADAR_REDDIT_SUBREDDITS", "")
    return [item.strip() for item in configured.split(",") if item.strip()]


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
        "hackathons": [
            ("algorithm contest", "Upcoming Codeforces contest window is open", "Codeforces", 70, "https://codeforces.com/contests"),
        ],
        "research": [
            ("agentic browser automation", "Agentic browser automation papers increase", "arXiv", 77, "https://arxiv.org"),
        ],
        "finance": [
            ("ai infrastructure", "Funding pulse favors AI infrastructure tooling", "YC Companies", 73, "https://www.ycombinator.com/companies"),
        ],
        "search": [
            ("browser agents", "Search results show browser agents startup pain", "DuckDuckGo", 67, "https://duckduckgo.com"),
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
            metadata={"days_left": 7} if category == "hackathons" else {},
        )
        for index, (topic, title, source, score, url) in enumerate(samples.get(category, []))
    ]
